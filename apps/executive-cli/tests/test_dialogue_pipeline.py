"""Tests for dialogue_pipeline.py — Sprint 2 Pipeline Engine implementation (ADR-12 / D3)."""
from __future__ import annotations

import pytest
from sqlmodel import Session, select

from executive_cli.db import get_engine
from executive_cli.ingest.dialogue_pipeline import (
    PIPELINE_NAME,
    ingest_dialogue_via_pipeline,
    register_dialogue_ingest_pipeline,
)
from executive_cli.ingest.types import ExtractedCandidate, CHANNEL_DIALOGUE
from executive_cli.models import IngestDocument, PipelineRun, Task


NOW = "2026-02-18T10:00:00+00:00"


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "test_dialogue_pipeline.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    engine = get_engine(ensure_directory=True)
    from typer.testing import CliRunner
    from executive_cli.cli import app as cli_app
    runner = CliRunner()
    runner.invoke(cli_app, ["init"])
    with Session(engine) as session:
        yield session


def _make_dialogue_file(tmp_path, content: str = "User: Schedule the call\nAssistant: Will do.") -> str:
    p = tmp_path / "dialogue.md"
    p.write_text(content)
    return str(p)


def _patch_extract(monkeypatch, candidates):
    """Monkeypatch extract_candidates to return fixed candidates."""
    monkeypatch.setattr(
        "executive_cli.ingest.dialogue_pipeline.extract_candidates",
        lambda **kwargs: candidates,
    )


# --- Tests ---


def test_pipeline_registration():
    """register_dialogue_ingest_pipeline adds dialogue_ingest to the registry."""
    from executive_cli.pipeline_engine import get_registered_pipelines
    register_dialogue_ingest_pipeline()
    assert PIPELINE_NAME in get_registered_pipelines()


def test_ingest_via_pipeline_auto_creates_task(db_session, monkeypatch, tmp_path):
    """High-confidence candidate from dialogue file → task auto-created via Pipeline Engine."""
    dialogue_file = _make_dialogue_file(tmp_path)

    _patch_extract(
        monkeypatch,
        [
            ExtractedCandidate(
                title="Schedule the call",
                suggested_status="NEXT",
                suggested_priority="P1",
                estimate_min=15,
                due_date=None,
                waiting_on=None,
                ping_at=None,
                commitment_hint=None,
                project_hint=None,
                confidence=0.95,
                rationale="explicit user request",
            )
        ],
    )

    summary = ingest_dialogue_via_pipeline(
        db_session, path=dialogue_file, title=None, now_iso=NOW
    )

    assert summary.auto_created == 1
    assert summary.drafted == 0
    assert summary.processed_documents == 1

    task = db_session.exec(select(Task).where(Task.title == "Schedule the call")).one()
    assert task is not None


def test_ingest_via_pipeline_drafts_low_confidence(db_session, monkeypatch, tmp_path):
    """Medium-confidence candidate → TaskDraft created."""
    dialogue_file = _make_dialogue_file(tmp_path)

    _patch_extract(
        monkeypatch,
        [
            ExtractedCandidate(
                title="Maybe look into automation",
                suggested_status="SOMEDAY",
                suggested_priority="P3",
                estimate_min=60,
                due_date=None,
                waiting_on=None,
                ping_at=None,
                commitment_hint=None,
                project_hint=None,
                confidence=0.5,
                rationale="vague mention",
            )
        ],
    )

    summary = ingest_dialogue_via_pipeline(
        db_session, path=dialogue_file, title=None, now_iso=NOW
    )

    assert summary.drafted == 1
    assert summary.auto_created == 0


def test_ingest_via_pipeline_skips_low_confidence(db_session, monkeypatch, tmp_path):
    """Below-threshold candidate (< 0.3) → skipped."""
    dialogue_file = _make_dialogue_file(tmp_path)

    _patch_extract(
        monkeypatch,
        [
            ExtractedCandidate(
                title="Unclear thing",
                suggested_status="SOMEDAY",
                suggested_priority="P3",
                estimate_min=5,
                due_date=None,
                waiting_on=None,
                ping_at=None,
                commitment_hint=None,
                project_hint=None,
                confidence=0.1,
                rationale="noise",
            )
        ],
    )

    summary = ingest_dialogue_via_pipeline(
        db_session, path=dialogue_file, title=None, now_iso=NOW
    )

    assert summary.skipped >= 1
    assert summary.auto_created == 0
    assert summary.drafted == 0


def test_ingest_via_pipeline_no_candidates(db_session, monkeypatch, tmp_path):
    """Dialogue file with no extracted candidates → processed, nothing created."""
    dialogue_file = _make_dialogue_file(tmp_path, content="General chit-chat only.")

    _patch_extract(monkeypatch, [])

    summary = ingest_dialogue_via_pipeline(
        db_session, path=dialogue_file, title=None, now_iso=NOW
    )

    assert summary.auto_created == 0
    assert summary.drafted == 0
    assert summary.extracted == 0
    assert summary.processed_documents == 1


def test_ingest_via_pipeline_idempotent(db_session, monkeypatch, tmp_path):
    """Running ingest twice on the same dialogue file doesn't re-create tasks."""
    dialogue_file = _make_dialogue_file(tmp_path)

    _patch_extract(
        monkeypatch,
        [
            ExtractedCandidate(
                title="Send project report",
                suggested_status="NEXT",
                suggested_priority="P1",
                estimate_min=20,
                due_date=None,
                waiting_on=None,
                ping_at=None,
                commitment_hint=None,
                project_hint=None,
                confidence=0.9,
                rationale="clear commitment",
            )
        ],
    )

    summary1 = ingest_dialogue_via_pipeline(
        db_session, path=dialogue_file, title=None, now_iso=NOW
    )
    assert summary1.auto_created == 1

    # Second run on same file — already processed
    summary2 = ingest_dialogue_via_pipeline(
        db_session, path=dialogue_file, title=None, now_iso=NOW
    )
    assert summary2.auto_created == 0

    tasks = db_session.exec(select(Task).where(Task.title == "Send project report")).all()
    assert len(tasks) == 1


def test_ingest_via_pipeline_file_not_found(db_session, monkeypatch, tmp_path):
    """Non-existent file → IngestProcessSummary with failed_documents=1."""
    missing_file = str(tmp_path / "missing_dialogue.md")

    summary = ingest_dialogue_via_pipeline(
        db_session, path=missing_file, title=None, now_iso=NOW
    )

    assert summary.failed_documents == 1
    assert summary.processed_documents == 0


def test_ingest_via_pipeline_creates_pipeline_run_record(db_session, monkeypatch, tmp_path):
    """Each dialogue file processed creates a PipelineRun record with status=completed."""
    dialogue_file = _make_dialogue_file(tmp_path)

    _patch_extract(monkeypatch, [])

    ingest_dialogue_via_pipeline(db_session, path=dialogue_file, title=None, now_iso=NOW)

    runs = db_session.exec(
        select(PipelineRun).where(PipelineRun.pipeline_name == PIPELINE_NAME)
    ).all()
    assert len(runs) >= 1
    assert all(r.status == "completed" for r in runs)


def test_ingest_via_pipeline_creates_ingest_document(db_session, monkeypatch, tmp_path):
    """Dialogue file ingest creates an IngestDocument with the correct channel."""
    dialogue_file = _make_dialogue_file(tmp_path)

    _patch_extract(monkeypatch, [])

    ingest_dialogue_via_pipeline(
        db_session, path=dialogue_file, title="Strategy Session", now_iso=NOW
    )

    docs = db_session.exec(
        select(IngestDocument).where(IngestDocument.channel == CHANNEL_DIALOGUE)
    ).all()
    assert len(docs) == 1
    assert docs[0].title == "Strategy Session"
    assert docs[0].status == "processed"


def test_ingest_via_pipeline_uses_stem_as_title(db_session, monkeypatch, tmp_path):
    """When no title is provided, the file stem is used as the document title."""
    p = tmp_path / "user_session_2026_02.md"
    p.write_text("User: Add reminder\nAssistant: Done.")
    _patch_extract(monkeypatch, [])

    ingest_dialogue_via_pipeline(db_session, path=str(p), title=None, now_iso=NOW)

    docs = db_session.exec(
        select(IngestDocument).where(IngestDocument.channel == CHANNEL_DIALOGUE)
    ).all()
    assert len(docs) == 1
    assert docs[0].title == "user_session_2026_02"
