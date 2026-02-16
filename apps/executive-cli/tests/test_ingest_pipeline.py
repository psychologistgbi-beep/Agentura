from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, select
from typer.testing import CliRunner

from executive_cli.cli import app
from executive_cli.db import get_engine
from executive_cli.ingest.types import DRAFT_STATUS_ACCEPTED, ExtractedCandidate
from executive_cli.models import Email, IngestDocument, IngestLog, Task, TaskDraft, TaskEmailLink, TaskPriority, TaskStatus


def test_ingest_meeting_review_and_accept_flow(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "ingest_meeting.sqlite"
    notes_path = tmp_path / "meeting.md"
    notes_path.write_text("TODO: Prepare offer by Friday", encoding="utf-8")

    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    runner = CliRunner()

    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0

    monkeypatch.setattr(
        "executive_cli.ingest.pipeline.extract_candidates",
        lambda **kwargs: [
            ExtractedCandidate(
                title="Prepare commercial offer",
                suggested_status="NEXT",
                suggested_priority="P2",
                estimate_min=45,
                due_date="2026-02-20",
                waiting_on=None,
                ping_at=None,
                commitment_hint=None,
                project_hint=None,
                confidence=0.6,
                rationale="explicit TODO",
            )
        ],
    )

    ingest_result = runner.invoke(app, ["ingest", "meeting", str(notes_path), "--title", "Weekly sync"])
    assert ingest_result.exit_code == 0
    assert "drafted=1" in ingest_result.output

    review_result = runner.invoke(app, ["ingest", "review"])
    assert review_result.exit_code == 0
    assert "Prepare commercial offer" in review_result.output

    accept_result = runner.invoke(app, ["ingest", "accept", "1"])
    assert accept_result.exit_code == 0
    assert "title=\"Prepare commercial offer\"" in accept_result.output

    with Session(get_engine(ensure_directory=True)) as session:
        task = session.exec(select(Task).where(Task.title == "Prepare commercial offer")).one()
        assert task.status == TaskStatus.NEXT

        draft = session.get(TaskDraft, 1)
        assert draft is not None
        assert draft.status == DRAFT_STATUS_ACCEPTED

        logs = session.exec(select(IngestLog).where(IngestLog.task_id == task.id)).all()
        assert any(log.action == "accepted_from_draft" for log in logs)


def test_ingest_email_auto_creates_task_and_origin_link(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "ingest_email.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    runner = CliRunner()

    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0

    with Session(get_engine(ensure_directory=True)) as session:
        session.add(
            Email(
                source="yandex_imap",
                external_id="<m1@example.com>",
                mailbox_uid=10,
                subject="Sign contract with customer",
                sender="alice@example.com",
                received_at="2026-02-20T09:00:00+00:00",
                first_seen_at="2026-02-20T09:00:00+00:00",
                last_seen_at="2026-02-20T09:00:00+00:00",
                flags_json='["\\\\Seen"]',
            )
        )
        session.commit()

    monkeypatch.setattr(
        "executive_cli.ingest.pipeline.extract_candidates",
        lambda **kwargs: [
            ExtractedCandidate(
                title="Sign contract with customer",
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

    ingest_result = runner.invoke(app, ["ingest", "email", "--limit", "5"])
    assert ingest_result.exit_code == 0
    assert "auto_created=1" in ingest_result.output

    with Session(get_engine(ensure_directory=True)) as session:
        task = session.exec(select(Task).where(Task.title == "Sign contract with customer")).one()
        assert task.priority == TaskPriority.P1
        links = session.exec(select(TaskEmailLink).where(TaskEmailLink.task_id == task.id)).all()
        assert len(links) == 1
        assert links[0].link_type == "origin"


def test_ingest_meeting_skips_exact_existing_task(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "ingest_dedup.sqlite"
    notes_path = tmp_path / "meeting.md"
    notes_path.write_text("TODO: Prepare pitch deck", encoding="utf-8")
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    runner = CliRunner()

    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0

    with Session(get_engine(ensure_directory=True)) as session:
        session.add(
            Task(
                title="Prepare pitch deck",
                status=TaskStatus.NEXT,
                priority=TaskPriority.P2,
                estimate_min=30,
            )
        )
        session.commit()

    monkeypatch.setattr(
        "executive_cli.ingest.pipeline.extract_candidates",
        lambda **kwargs: [
            ExtractedCandidate(
                title="Prepare pitch deck",
                suggested_status="NEXT",
                suggested_priority="P2",
                estimate_min=30,
                due_date=None,
                waiting_on=None,
                ping_at=None,
                commitment_hint=None,
                project_hint=None,
                confidence=0.95,
                rationale="duplicate",
            )
        ],
    )

    ingest_result = runner.invoke(app, ["ingest", "meeting", str(notes_path)])
    assert ingest_result.exit_code == 0
    assert "skipped=1" in ingest_result.output

    with Session(get_engine(ensure_directory=True)) as session:
        docs = session.exec(select(IngestDocument)).all()
        assert len(docs) == 1
        tasks = session.exec(select(Task).where(Task.title == "Prepare pitch deck")).all()
        assert len(tasks) == 1
