"""Dialogue Ingest Pipeline — Pipeline Engine implementation (ADR-12 / D3).

Processes assistant dialogue files as a registered Pipeline Engine pipeline.
Each file is processed as a separate pipeline run with steps:
  1. parse          — read file, build raw_text + context; create IngestDocument  (deterministic)
  2. extract        — call LLM to extract task candidates                         (llm, retry=1)
  3. classify_route — classify, dedup, and route each candidate                   (deterministic)

Backward compatibility: `ingest_dialogue_file()` in pipeline.py still works as before.
This module provides `ingest_dialogue_via_pipeline()` as the Pipeline Engine alternative.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from sqlmodel import Session, select

from executive_cli.db import DEFAULT_SETTINGS
from executive_cli.ingest.classifier import classify_candidates
from executive_cli.ingest.dedup import detect_dedup
from executive_cli.ingest.extractor import LLMClientError, extract_candidates
from executive_cli.ingest.router import route_candidate
from executive_cli.ingest.types import (
    CHANNEL_DIALOGUE,
    DOC_STATUS_FAILED,
    DOC_STATUS_PENDING,
    DOC_STATUS_PROCESSED,
    IngestProcessSummary,
)
from executive_cli.models import IngestDocument, Settings
from executive_cli.pipeline_engine import (
    PipelineDefinition,
    StepContext,
    StepDefinition,
    StepResult,
    register_pipeline,
    run_pipeline,
)

PIPELINE_NAME = "dialogue_ingest"


# --- Step handlers ---


def _step_parse(ctx: StepContext) -> StepResult:
    """Read dialogue file, create IngestDocument, and prepare raw text for extraction."""
    session = ctx.session
    file_path_str = ctx.input_data["file_path"]
    now_iso = ctx.input_data["now_iso"]
    title_hint = ctx.input_data.get("title")

    path = Path(file_path_str).expanduser().resolve()
    source_ref = str(path)
    title = title_hint or path.stem

    # Check if already processed
    existing = session.exec(
        select(IngestDocument).where(
            IngestDocument.channel == CHANNEL_DIALOGUE,
            IngestDocument.source_ref == source_ref,
        )
    ).first()
    if existing is not None and existing.status == DOC_STATUS_PROCESSED:
        return StepResult(
            status="completed",
            output_data={"skipped": True, "reason": "already_processed"},
        )

    # Validate file exists
    if not path.exists() or not path.is_file():
        return StepResult(status="failed", error=f"File not found: {path}")

    doc = IngestDocument(
        channel=CHANNEL_DIALOGUE,
        source_ref=source_ref,
        title=title,
        status=DOC_STATUS_PENDING,
        created_at=now_iso,
    )
    session.add(doc)
    session.flush()

    raw_text = path.read_text(encoding="utf-8")
    context = {
        "source_ref": source_ref,
        "title": title,
    }

    return StepResult(
        status="completed",
        output_data={
            "document_id": doc.id,
            "raw_text": raw_text,
            "context": context,
            "file_path": file_path_str,
        },
    )


def _step_extract(ctx: StepContext) -> StepResult:
    """Extract task candidates from dialogue text using LLM."""
    if ctx.input_data.get("skipped"):
        return StepResult(status="completed", output_data={"skipped": True})

    raw_text = ctx.input_data["raw_text"]
    context = ctx.input_data["context"]
    document_id = ctx.input_data["document_id"]
    session = ctx.session

    provider, model, temperature, _ = _load_ingest_settings(session)

    try:
        candidates = extract_candidates(
            raw_text=raw_text,
            source_channel=CHANNEL_DIALOGUE,
            context=context,
            provider=provider,
            model=model,
            temperature=temperature,
        )
    except LLMClientError as exc:
        # Mark document as pending (LLM unavailable) — not a hard failure
        doc = session.get(IngestDocument, document_id)
        if doc is not None:
            doc.status = DOC_STATUS_PENDING
            doc.items_extracted = None
            doc.processed_at = None
            session.add(doc)
        return StepResult(status="failed", error=f"LLM extraction failed: {exc}")

    # Serialize candidates for the next step
    serialized = [
        {
            "title": c.title,
            "suggested_status": c.suggested_status,
            "suggested_priority": c.suggested_priority,
            "estimate_min": c.estimate_min,
            "due_date": c.due_date,
            "waiting_on": c.waiting_on,
            "ping_at": c.ping_at,
            "commitment_hint": c.commitment_hint,
            "project_hint": c.project_hint,
            "confidence": c.confidence,
            "rationale": c.rationale,
        }
        for c in candidates
    ]

    return StepResult(
        status="completed",
        output_data={
            "candidates": serialized,
            "candidate_count": len(serialized),
            "document_id": document_id,
            "file_path": ctx.input_data.get("file_path"),
        },
    )


def _step_classify_route(ctx: StepContext) -> StepResult:
    """Classify, deduplicate, and route all extracted candidates."""
    if ctx.input_data.get("skipped"):
        return StepResult(
            status="completed",
            output_data={"auto_created": 0, "drafted": 0, "skipped": 1},
        )

    session = ctx.session
    document_id = ctx.input_data.get("document_id")
    now_iso = ctx.input_data.get("now_iso", "")
    raw_candidates = ctx.input_data.get("candidates", [])

    if not raw_candidates:
        # No candidates — mark document processed
        doc = session.get(IngestDocument, document_id)
        if doc is not None:
            doc.status = DOC_STATUS_PROCESSED
            doc.items_extracted = 0
            doc.processed_at = now_iso
            session.add(doc)
        return StepResult(
            status="completed",
            output_data={"auto_created": 0, "drafted": 0, "skipped": 0, "extracted": 0},
        )

    # Deserialize candidates
    from executive_cli.ingest.types import ExtractedCandidate

    extracted = [
        ExtractedCandidate(
            title=c["title"],
            suggested_status=c.get("suggested_status"),
            suggested_priority=c.get("suggested_priority"),
            estimate_min=c.get("estimate_min"),
            due_date=c.get("due_date"),
            waiting_on=c.get("waiting_on"),
            ping_at=c.get("ping_at"),
            commitment_hint=c.get("commitment_hint"),
            project_hint=c.get("project_hint"),
            confidence=c.get("confidence", 0.0),
            rationale=c.get("rationale"),
        )
        for c in raw_candidates
    ]

    # Classify
    classified = classify_candidates(
        session,
        candidates=extracted,
        source_channel=CHANNEL_DIALOGUE,
        source_document_id=document_id,
        source_email_id=None,
    )

    # Load threshold
    _, _, _, auto_threshold = _load_ingest_settings(session)

    # Dedup + route each candidate
    auto_created = 0
    drafted = 0
    skipped = 0
    for candidate in classified:
        dedup = detect_dedup(
            session,
            candidate_title=candidate.title,
            source_document_id=candidate.source_document_id,
            source_email_id=candidate.source_email_id,
        )
        outcome = route_candidate(
            session,
            candidate=replace(candidate, dedup_flag=dedup.dedup_flag),
            dedup=dedup,
            auto_threshold=auto_threshold,
            now_iso=now_iso,
        )
        auto_created += outcome.auto_created
        drafted += outcome.drafted
        skipped += outcome.skipped

    # Mark document processed
    doc = session.get(IngestDocument, document_id)
    if doc is not None:
        doc.status = DOC_STATUS_PROCESSED
        doc.items_extracted = len(extracted)
        doc.processed_at = now_iso
        session.add(doc)

    return StepResult(
        status="completed",
        output_data={
            "extracted": len(extracted),
            "auto_created": auto_created,
            "drafted": drafted,
            "skipped": skipped,
        },
    )


# --- Pipeline registration ---


def register_dialogue_ingest_pipeline() -> None:
    """Register the dialogue_ingest pipeline definition."""
    definition = PipelineDefinition(
        name=PIPELINE_NAME,
        steps=[
            StepDefinition(
                name="parse",
                handler=_step_parse,
                step_type="deterministic",
            ),
            StepDefinition(
                name="extract",
                handler=_step_extract,
                step_type="llm",
                max_retries=1,
                backoff_seconds=2.0,
            ),
            StepDefinition(
                name="classify_route",
                handler=_step_classify_route,
                step_type="deterministic",
            ),
        ],
    )
    register_pipeline(definition)


# --- Public entry point ---


def ingest_dialogue_via_pipeline(
    session: Session,
    *,
    path: str,
    title: str | None,
    now_iso: str,
) -> IngestProcessSummary:
    """Process a dialogue file using the Pipeline Engine.

    Drop-in replacement for `ingest_dialogue_file()` that routes through
    the Pipeline Engine for traceability, retry, and idempotency.
    """
    register_dialogue_ingest_pipeline()

    result = run_pipeline(
        session,
        pipeline_name=PIPELINE_NAME,
        input_data={
            "file_path": path,
            "title": title,
            "now_iso": now_iso,
        },
        now_iso=now_iso,
    )

    session.commit()

    if result.status == "completed" and result.output_data:
        out = result.output_data
        if out.get("skipped"):
            return IngestProcessSummary(processed_documents=0, skipped=1)
        return IngestProcessSummary(
            processed_documents=1,
            failed_documents=0,
            pending_documents=0,
            extracted=out.get("extracted", 0),
            auto_created=out.get("auto_created", 0),
            drafted=out.get("drafted", 0),
            skipped=out.get("skipped", 0),
        )
    elif result.status == "failed":
        return IngestProcessSummary(failed_documents=1)
    elif result.status == "waiting_approval":
        return IngestProcessSummary(pending_documents=1)

    return IngestProcessSummary()


# --- Helpers ---


def _load_ingest_settings(session: Session) -> tuple[str, str, float, float]:
    provider = _read_setting(session, "ingest_llm_provider")
    model = _read_setting(session, "ingest_llm_model")
    temperature = _parse_float(_read_setting(session, "ingest_llm_temperature"), fallback=0.0)
    threshold = _parse_float(_read_setting(session, "ingest_auto_threshold"), fallback=0.8)
    threshold = max(0.0, min(1.0, threshold))
    return provider, model, temperature, threshold


def _read_setting(session: Session, key: str) -> str:
    setting = session.get(Settings, key)
    if setting is not None:
        return setting.value
    return DEFAULT_SETTINGS[key]


def _parse_float(raw: str, *, fallback: float) -> float:
    try:
        return float(raw)
    except ValueError:
        return fallback
