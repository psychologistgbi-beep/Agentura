"""Tests for meeting_pipeline.py — Sprint 2 Pipeline Engine implementation (ADR-12 / D2)."""
from __future__ import annotations

import pytest
from sqlmodel import Session, select

from executive_cli.db import get_engine
from executive_cli.ingest.meeting_pipeline import (
    PIPELINE_NAME,
    ingest_meeting_via_pipeline,
    register_meeting_ingest_pipeline,
)
from executive_cli.ingest.types import ExtractedCandidate, CHANNEL_MEETING
from executive_cli.models import IngestDocument, PipelineRun, Task


NOW = "2026-02-18T10:00:00+00:00"


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "test_meeting_pipeline.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    engine = get_engine(ensure_directory=True)
    from typer.testing import CliRunner
    from executive_cli.cli import app as cli_app
    runner = CliRunner()
    runner.invoke(cli_app, ["init"])
    with Session(engine) as session:
        yield session


def _make_meeting_file(tmp_path, content: str = "Action: Schedule team review\nAction: Prepare slides") -> str:
    p = tmp_path / "meeting_notes.md"
    p.write_text(content)
    return str(p)


def _patch_extract(monkeypatch, candidates):
    """Monkeypatch extract_candidates to return fixed candidates."""
    monkeypatch.setattr(
        "executive_cli.ingest.meeting_pipeline.extract_candidates",
        lambda **kwargs: candidates,
    )


# --- Tests ---


def test_pipeline_registration():
    """register_meeting_ingest_pipeline adds meeting_ingest to the registry."""
    from executive_cli.pipeline_engine import get_registered_pipelines
    register_meeting_ingest_pipeline()
    assert PIPELINE_NAME in get_registered_pipelines()


def test_ingest_via_pipeline_auto_creates_task(db_session, monkeypatch, tmp_path):
    """High-confidence candidate from meeting file → task auto-created via Pipeline Engine."""
    meeting_file = _make_meeting_file(tmp_path)

    _patch_extract(
        monkeypatch,
        [
            ExtractedCandidate(
                title="Schedule team review",
                suggested_status="NEXT",
                suggested_priority="P1",
                estimate_min=30,
                due_date=None,
                waiting_on=None,
                ping_at=None,
                commitment_hint=None,
                project_hint=None,
                confidence=0.95,
                rationale="clear action from meeting",
            )
        ],
    )

    summary = ingest_meeting_via_pipeline(
        db_session, path=meeting_file, title=None, now_iso=NOW
    )

    assert summary.auto_created == 1
    assert summary.drafted == 0
    assert summary.processed_documents == 1

    task = db_session.exec(select(Task).where(Task.title == "Schedule team review")).one()
    assert task is not None


def test_ingest_via_pipeline_drafts_low_confidence(db_session, monkeypatch, tmp_path):
    """Medium-confidence candidate → TaskDraft created."""
    meeting_file = _make_meeting_file(tmp_path)

    _patch_extract(
        monkeypatch,
        [
            ExtractedCandidate(
                title="Maybe send follow-up email",
                suggested_status="NEXT",
                suggested_priority="P2",
                estimate_min=10,
                due_date=None,
                waiting_on=None,
                ping_at=None,
                commitment_hint=None,
                project_hint=None,
                confidence=0.5,
                rationale="uncertain item",
            )
        ],
    )

    summary = ingest_meeting_via_pipeline(
        db_session, path=meeting_file, title=None, now_iso=NOW
    )

    assert summary.drafted == 1
    assert summary.auto_created == 0


def test_ingest_via_pipeline_skips_low_confidence(db_session, monkeypatch, tmp_path):
    """Below-threshold candidate (< 0.3) → skipped."""
    meeting_file = _make_meeting_file(tmp_path)

    _patch_extract(
        monkeypatch,
        [
            ExtractedCandidate(
                title="Vague mention",
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

    summary = ingest_meeting_via_pipeline(
        db_session, path=meeting_file, title=None, now_iso=NOW
    )

    assert summary.skipped >= 1
    assert summary.auto_created == 0
    assert summary.drafted == 0


def test_ingest_via_pipeline_no_candidates(db_session, monkeypatch, tmp_path):
    """Meeting file with no extracted candidates → processed, nothing created."""
    meeting_file = _make_meeting_file(tmp_path, content="General discussion notes only.")

    _patch_extract(monkeypatch, [])

    summary = ingest_meeting_via_pipeline(
        db_session, path=meeting_file, title=None, now_iso=NOW
    )

    assert summary.auto_created == 0
    assert summary.drafted == 0
    assert summary.extracted == 0
    assert summary.processed_documents == 1


def test_ingest_via_pipeline_idempotent(db_session, monkeypatch, tmp_path):
    """Running ingest twice on the same meeting file doesn't re-create tasks."""
    meeting_file = _make_meeting_file(tmp_path)

    _patch_extract(
        monkeypatch,
        [
            ExtractedCandidate(
                title="Deploy new feature",
                suggested_status="NEXT",
                suggested_priority="P1",
                estimate_min=60,
                due_date=None,
                waiting_on=None,
                ping_at=None,
                commitment_hint=None,
                project_hint=None,
                confidence=0.9,
                rationale="explicit decision",
            )
        ],
    )

    summary1 = ingest_meeting_via_pipeline(
        db_session, path=meeting_file, title=None, now_iso=NOW
    )
    assert summary1.auto_created == 1

    # Second run on same file — already processed
    summary2 = ingest_meeting_via_pipeline(
        db_session, path=meeting_file, title=None, now_iso=NOW
    )
    assert summary2.auto_created == 0

    tasks = db_session.exec(select(Task).where(Task.title == "Deploy new feature")).all()
    assert len(tasks) == 1


def test_ingest_via_pipeline_file_not_found(db_session, monkeypatch, tmp_path):
    """Non-existent file → IngestProcessSummary with failed_documents=1."""
    missing_file = str(tmp_path / "nonexistent.md")

    summary = ingest_meeting_via_pipeline(
        db_session, path=missing_file, title=None, now_iso=NOW
    )

    assert summary.failed_documents == 1
    assert summary.processed_documents == 0


def test_ingest_via_pipeline_creates_pipeline_run_record(db_session, monkeypatch, tmp_path):
    """Each meeting file processed creates a PipelineRun record with status=completed."""
    meeting_file = _make_meeting_file(tmp_path)

    _patch_extract(monkeypatch, [])

    ingest_meeting_via_pipeline(db_session, path=meeting_file, title=None, now_iso=NOW)

    runs = db_session.exec(
        select(PipelineRun).where(PipelineRun.pipeline_name == PIPELINE_NAME)
    ).all()
    assert len(runs) >= 1
    assert all(r.status == "completed" for r in runs)


def test_ingest_via_pipeline_creates_ingest_document(db_session, monkeypatch, tmp_path):
    """Meeting file ingest creates an IngestDocument with the correct channel."""
    meeting_file = _make_meeting_file(tmp_path)

    _patch_extract(monkeypatch, [])

    ingest_meeting_via_pipeline(db_session, path=meeting_file, title="Q1 Kickoff", now_iso=NOW)

    docs = db_session.exec(
        select(IngestDocument).where(IngestDocument.channel == CHANNEL_MEETING)
    ).all()
    assert len(docs) == 1
    assert docs[0].title == "Q1 Kickoff"
    assert docs[0].status == "processed"


def test_ingest_via_pipeline_uses_stem_as_title(db_session, monkeypatch, tmp_path):
    """When no title is provided, the file stem is used as the document title."""
    p = tmp_path / "q2_planning_notes.md"
    p.write_text("Action: Review budget")
    _patch_extract(monkeypatch, [])

    ingest_meeting_via_pipeline(db_session, path=str(p), title=None, now_iso=NOW)

    docs = db_session.exec(
        select(IngestDocument).where(IngestDocument.channel == CHANNEL_MEETING)
    ).all()
    assert len(docs) == 1
    assert docs[0].title == "q2_planning_notes"
