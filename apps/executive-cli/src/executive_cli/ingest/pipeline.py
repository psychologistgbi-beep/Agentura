from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

from sqlmodel import Session, select

from executive_cli.db import DEFAULT_SETTINGS
from executive_cli.ingest.classifier import classify_candidates
from executive_cli.ingest.dedup import detect_dedup
from executive_cli.ingest.extractor import LLMClientError, extract_candidates
from executive_cli.ingest.router import RouteOutcome, route_candidate
from executive_cli.ingest.types import (
    CHANNEL_DIALOGUE,
    CHANNEL_EMAIL,
    CHANNEL_MEETING,
    DOC_STATUS_FAILED,
    DOC_STATUS_PENDING,
    DOC_STATUS_PROCESSED,
    IngestProcessSummary,
)
from executive_cli.models import Email, IngestDocument, Settings


def ingest_meeting_file(
    session: Session,
    *,
    path: str,
    title: str | None,
    now_iso: str,
) -> IngestProcessSummary:
    return _ingest_file_document(
        session,
        path=path,
        title=title,
        channel=CHANNEL_MEETING,
        now_iso=now_iso,
    )


def ingest_dialogue_file(
    session: Session,
    *,
    path: str,
    title: str | None,
    now_iso: str,
) -> IngestProcessSummary:
    return _ingest_file_document(
        session,
        path=path,
        title=title,
        channel=CHANNEL_DIALOGUE,
        now_iso=now_iso,
    )


def ingest_email_channel(
    session: Session,
    *,
    since: date | None,
    limit: int,
    now_iso: str,
) -> IngestProcessSummary:
    if limit < 1:
        limit = 1

    all_emails = session.exec(select(Email).order_by(Email.id)).all()
    existing_refs = {
        doc.source_ref
        for doc in session.exec(
            select(IngestDocument).where(IngestDocument.channel == CHANNEL_EMAIL)
        ).all()
    }

    processed = 0
    failed = 0
    pending = 0
    extracted = 0
    auto_created = 0
    drafted = 0
    skipped = 0
    examined = 0

    for email in all_emails:
        if examined >= limit:
            break
        if str(email.id) in existing_refs:
            continue
        if since is not None and not _email_received_on_or_after(email.received_at, since):
            continue

        doc = IngestDocument(
            channel=CHANNEL_EMAIL,
            source_ref=str(email.id),
            title=email.subject,
            status=DOC_STATUS_PENDING,
            created_at=now_iso,
        )
        session.add(doc)
        session.flush()

        raw_text = f"From: {email.sender or '-'}\nSubject: {email.subject or '-'}"
        context = {
            "source_ref": str(email.id),
            "sender": email.sender or "",
            "subject": email.subject or "",
        }
        result = _process_document(
            session,
            document=doc,
            raw_text=raw_text,
            source_channel=CHANNEL_EMAIL,
            source_email_id=email.id,
            context=context,
            now_iso=now_iso,
        )
        processed += result.processed_documents
        failed += result.failed_documents
        pending += result.pending_documents
        extracted += result.extracted
        auto_created += result.auto_created
        drafted += result.drafted
        skipped += result.skipped
        examined += 1

    session.commit()
    return IngestProcessSummary(
        processed_documents=processed,
        failed_documents=failed,
        pending_documents=pending,
        extracted=extracted,
        auto_created=auto_created,
        drafted=drafted,
        skipped=skipped,
    )


def _ingest_file_document(
    session: Session,
    *,
    path: str,
    title: str | None,
    channel: str,
    now_iso: str,
) -> IngestProcessSummary:
    source_path = str(Path(path).expanduser().resolve())
    existing = session.exec(
        select(IngestDocument).where(
            IngestDocument.channel == channel,
            IngestDocument.source_ref == source_path,
        )
    ).first()
    if existing is not None and existing.status == DOC_STATUS_PROCESSED:
        return IngestProcessSummary(processed_documents=0)

    document = existing
    if document is None:
        document = IngestDocument(
            channel=channel,
            source_ref=source_path,
            title=title,
            status=DOC_STATUS_PENDING,
            created_at=now_iso,
        )
        session.add(document)
        session.flush()

    file_path = Path(source_path)
    if not file_path.exists() or not file_path.is_file():
        document.status = DOC_STATUS_FAILED
        document.processed_at = now_iso
        document.items_extracted = 0
        session.add(document)
        session.commit()
        return IngestProcessSummary(failed_documents=1)

    raw_text = file_path.read_text(encoding="utf-8")
    summary = _process_document(
        session,
        document=document,
        raw_text=raw_text,
        source_channel=channel,
        source_email_id=None,
        context={"source_ref": source_path, "title": title or ""},
        now_iso=now_iso,
    )
    session.commit()
    return summary


def _process_document(
    session: Session,
    *,
    document: IngestDocument,
    raw_text: str,
    source_channel: str,
    source_email_id: int | None,
    context: dict[str, str],
    now_iso: str,
) -> IngestProcessSummary:
    provider, model, temperature, auto_threshold = _load_ingest_settings(session)

    try:
        extracted_candidates = extract_candidates(
            raw_text=raw_text,
            source_channel=source_channel,
            context=context,
            provider=provider,
            model=model,
            temperature=temperature,
        )
    except LLMClientError:
        document.status = DOC_STATUS_PENDING
        document.items_extracted = None
        document.processed_at = None
        session.add(document)
        return IngestProcessSummary(pending_documents=1)

    classified = classify_candidates(
        session,
        candidates=extracted_candidates,
        source_channel=source_channel,
        source_document_id=document.id,
        source_email_id=source_email_id,
    )

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

    document.status = DOC_STATUS_PROCESSED
    document.items_extracted = len(extracted_candidates)
    document.processed_at = now_iso
    session.add(document)

    return IngestProcessSummary(
        processed_documents=1,
        extracted=len(extracted_candidates),
        auto_created=auto_created,
        drafted=drafted,
        skipped=skipped,
    )


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


def _email_received_on_or_after(received_at: str | None, since: date) -> bool:
    if not received_at:
        return False
    try:
        parsed = datetime.fromisoformat(received_at)
    except ValueError:
        return False
    return parsed.date() >= since
