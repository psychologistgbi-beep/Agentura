"""Tests for email_pipeline.py — D6 proof-of-concept on Pipeline Engine."""
from __future__ import annotations

from datetime import date

import pytest
from sqlmodel import Session, select

from executive_cli.db import get_engine
from executive_cli.ingest.email_pipeline import (
    PIPELINE_NAME,
    ingest_email_via_pipeline,
    register_email_ingest_pipeline,
)
from executive_cli.ingest.types import ExtractedCandidate
from executive_cli.models import Email, IngestDocument, PipelineRun, Task, TaskEmailLink


NOW = "2026-02-18T10:00:00+00:00"


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "test_email_pipeline.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    engine = get_engine(ensure_directory=True)
    # run init migrations via CLI to get all tables
    from typer.testing import CliRunner
    from executive_cli.cli import app as cli_app
    runner = CliRunner()
    runner.invoke(cli_app, ["init"])
    with Session(engine) as session:
        yield session


def _add_email(session: Session, *, email_id_hint: str = "m1@example.com", subject: str = "Do the thing") -> Email:
    email = Email(
        source="yandex_imap",
        external_id=f"<{email_id_hint}>",
        mailbox_uid=1,
        subject=subject,
        sender="boss@example.com",
        received_at="2026-02-18T08:00:00+00:00",
        first_seen_at="2026-02-18T08:00:00+00:00",
        last_seen_at="2026-02-18T08:00:00+00:00",
        flags_json="[]",
    )
    session.add(email)
    session.flush()
    return email


def _patch_extract(monkeypatch, candidates):
    """Monkeypatch extract_candidates to return fixed candidates."""
    monkeypatch.setattr(
        "executive_cli.ingest.email_pipeline.extract_candidates",
        lambda **kwargs: candidates,
    )


# --- Tests ---


def test_pipeline_registration():
    """register_email_ingest_pipeline adds email_ingest to the registry."""
    from executive_cli.pipeline_engine import get_registered_pipelines
    register_email_ingest_pipeline()
    assert PIPELINE_NAME in get_registered_pipelines()


def test_ingest_via_pipeline_auto_creates_task(db_session, monkeypatch):
    """High-confidence candidate → task auto-created via Pipeline Engine."""
    email = _add_email(db_session, subject="Sign vendor contract")
    db_session.commit()

    _patch_extract(
        monkeypatch,
        [
            ExtractedCandidate(
                title="Sign vendor contract",
                suggested_status="NEXT",
                suggested_priority="P1",
                estimate_min=30,
                due_date=None,
                waiting_on=None,
                ping_at=None,
                commitment_hint=None,
                project_hint=None,
                confidence=0.95,
                rationale="clear action in subject",
            )
        ],
    )

    summary = ingest_email_via_pipeline(db_session, since=None, limit=10, now_iso=NOW)

    assert summary.auto_created == 1
    assert summary.drafted == 0
    assert summary.processed_documents == 1

    task = db_session.exec(select(Task).where(Task.title == "Sign vendor contract")).one()
    assert task is not None

    links = db_session.exec(select(TaskEmailLink).where(TaskEmailLink.task_id == task.id)).all()
    assert len(links) == 1
    assert links[0].link_type == "origin"
    assert links[0].email_id == email.id


def test_ingest_via_pipeline_drafts_low_confidence(db_session, monkeypatch):
    """Medium-confidence candidate → TaskDraft created."""
    _add_email(db_session, subject="Maybe review something")
    db_session.commit()

    _patch_extract(
        monkeypatch,
        [
            ExtractedCandidate(
                title="Review something",
                suggested_status="NEXT",
                suggested_priority="P2",
                estimate_min=20,
                due_date=None,
                waiting_on=None,
                ping_at=None,
                commitment_hint=None,
                project_hint=None,
                confidence=0.5,
                rationale="uncertain",
            )
        ],
    )

    summary = ingest_email_via_pipeline(db_session, since=None, limit=10, now_iso=NOW)

    assert summary.drafted == 1
    assert summary.auto_created == 0


def test_ingest_via_pipeline_skips_low_confidence(db_session, monkeypatch):
    """Below-threshold candidate (< 0.3) → skipped."""
    _add_email(db_session, subject="Noise email")
    db_session.commit()

    _patch_extract(
        monkeypatch,
        [
            ExtractedCandidate(
                title="Maybe something",
                suggested_status="NEXT",
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

    summary = ingest_email_via_pipeline(db_session, since=None, limit=10, now_iso=NOW)

    assert summary.skipped >= 1
    assert summary.auto_created == 0
    assert summary.drafted == 0


def test_ingest_via_pipeline_no_candidates(db_session, monkeypatch):
    """Email with no extracted candidates → processed, nothing created."""
    _add_email(db_session, subject="FYI newsletter")
    db_session.commit()

    _patch_extract(monkeypatch, [])

    summary = ingest_email_via_pipeline(db_session, since=None, limit=10, now_iso=NOW)

    assert summary.auto_created == 0
    assert summary.drafted == 0
    assert summary.extracted == 0
    assert summary.processed_documents == 1


def test_ingest_via_pipeline_idempotent(db_session, monkeypatch):
    """Running ingest twice on the same email doesn't re-create tasks."""
    _add_email(db_session, subject="Deploy to staging")
    db_session.commit()

    _patch_extract(
        monkeypatch,
        [
            ExtractedCandidate(
                title="Deploy to staging",
                suggested_status="NEXT",
                suggested_priority="P1",
                estimate_min=15,
                due_date=None,
                waiting_on=None,
                ping_at=None,
                commitment_hint=None,
                project_hint=None,
                confidence=0.9,
                rationale="explicit action",
            )
        ],
    )

    summary1 = ingest_email_via_pipeline(db_session, since=None, limit=10, now_iso=NOW)
    assert summary1.auto_created == 1

    # Second run — same email, already in ingest_documents
    summary2 = ingest_email_via_pipeline(db_session, since=None, limit=10, now_iso=NOW)
    assert summary2.auto_created == 0

    tasks = db_session.exec(select(Task).where(Task.title == "Deploy to staging")).all()
    assert len(tasks) == 1


def test_ingest_via_pipeline_since_filter(db_session, monkeypatch):
    """The `since` filter excludes emails before the date."""
    email = Email(
        source="yandex_imap",
        external_id="<old@example.com>",
        mailbox_uid=2,
        subject="Old task",
        sender="boss@example.com",
        received_at="2026-01-01T08:00:00+00:00",
        first_seen_at="2026-01-01T08:00:00+00:00",
        last_seen_at="2026-01-01T08:00:00+00:00",
        flags_json="[]",
    )
    db_session.add(email)
    db_session.commit()

    _patch_extract(
        monkeypatch,
        [
            ExtractedCandidate(
                title="Old task",
                suggested_status="NEXT",
                suggested_priority="P2",
                estimate_min=15,
                due_date=None,
                waiting_on=None,
                ping_at=None,
                commitment_hint=None,
                project_hint=None,
                confidence=0.9,
                rationale="old",
            )
        ],
    )

    summary = ingest_email_via_pipeline(
        db_session,
        since=date(2026, 2, 1),  # only Feb 2026 onwards
        limit=10,
        now_iso=NOW,
    )

    assert summary.auto_created == 0
    assert summary.processed_documents == 0


def test_ingest_via_pipeline_creates_pipeline_run_record(db_session, monkeypatch):
    """Each email processed creates a PipelineRun record with status=completed."""
    _add_email(db_session, subject="Review proposal")
    db_session.commit()

    _patch_extract(monkeypatch, [])

    ingest_email_via_pipeline(db_session, since=None, limit=10, now_iso=NOW)

    runs = db_session.exec(
        select(PipelineRun).where(PipelineRun.pipeline_name == PIPELINE_NAME)
    ).all()
    assert len(runs) >= 1
    assert all(r.status == "completed" for r in runs)


def test_ingest_via_pipeline_limit(db_session, monkeypatch):
    """The `limit` parameter caps how many emails are processed."""
    for i in range(5):
        email = Email(
            source="yandex_imap",
            external_id=f"<e{i}@example.com>",
            mailbox_uid=10 + i,
            subject=f"Task {i}",
            sender="boss@example.com",
            received_at="2026-02-18T08:00:00+00:00",
            first_seen_at="2026-02-18T08:00:00+00:00",
            last_seen_at="2026-02-18T08:00:00+00:00",
            flags_json="[]",
        )
        db_session.add(email)
    db_session.commit()

    _patch_extract(monkeypatch, [])

    summary = ingest_email_via_pipeline(db_session, since=None, limit=2, now_iso=NOW)

    runs = db_session.exec(
        select(PipelineRun).where(PipelineRun.pipeline_name == PIPELINE_NAME)
    ).all()
    assert len(runs) == 2
    assert summary.processed_documents + summary.skipped <= 2
