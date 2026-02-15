from __future__ import annotations

from sqlmodel import Session, select
from typer.testing import CliRunner

from executive_cli.cli import app
from executive_cli.db import get_engine
from executive_cli.models import Email, Task, TaskEmailLink, TaskPriority, TaskStatus


def _init_db(tmp_path, monkeypatch) -> CliRunner:
    db_path = tmp_path / "task_email.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    runner = CliRunner()
    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0
    return runner


def _seed_email(
    *,
    source: str = "yandex_imap",
    external_id: str = "<mail-1@example.com>",
    subject: str | None = "Need follow-up",
    sender: str = "alice@example.com",
    received_at: str = "2026-02-20T09:00:00+00:00",
) -> int:
    with Session(get_engine(ensure_directory=True)) as session:
        email = Email(
            source=source,
            external_id=external_id,
            mailbox_uid=101,
            subject=subject,
            sender=sender,
            received_at=received_at,
            first_seen_at="2026-02-20T09:01:00+00:00",
            last_seen_at="2026-02-20T09:01:00+00:00",
            flags_json='["\\\\Seen"]',
        )
        session.add(email)
        session.commit()
        session.refresh(email)
        return email.id


def test_task_capture_from_email_creates_task_with_defaults_and_origin_link(tmp_path, monkeypatch) -> None:
    runner = _init_db(tmp_path, monkeypatch)
    email_id = _seed_email(subject="Reply to Alice")

    result = runner.invoke(app, ["task", "capture", "--from-email", str(email_id)])
    assert result.exit_code == 0
    assert "status=NEXT" in result.output
    assert "priority=P2" in result.output
    assert "estimate=30" in result.output
    assert 'title="Reply to Alice"' in result.output

    with Session(get_engine(ensure_directory=True)) as session:
        task = session.exec(select(Task)).one()
        assert task.status == TaskStatus.NEXT
        assert task.priority == TaskPriority.P2
        assert task.estimate_min == 30
        assert task.title == "Reply to Alice"

        links = session.exec(select(TaskEmailLink).where(TaskEmailLink.task_id == task.id)).all()
        assert len(links) == 1
        assert links[0].email_id == email_id
        assert links[0].link_type == "origin"


def test_task_capture_from_email_uses_subject_fallback(tmp_path, monkeypatch) -> None:
    runner = _init_db(tmp_path, monkeypatch)
    email_id = _seed_email(subject=None)

    result = runner.invoke(app, ["task", "capture", "--from-email", str(email_id)])
    assert result.exit_code == 0
    assert 'title="Email follow-up"' in result.output


def test_task_link_email_duplicate_pair_returns_friendly_error(tmp_path, monkeypatch) -> None:
    runner = _init_db(tmp_path, monkeypatch)
    email_id = _seed_email()

    task_result = runner.invoke(
        app,
        ["task", "capture", "Prepare update", "--estimate", "45", "--priority", "P1", "--status", "NEXT"],
    )
    assert task_result.exit_code == 0

    with Session(get_engine(ensure_directory=True)) as session:
        task = session.exec(select(Task).where(Task.title == "Prepare update")).one()
        task_id = task.id

    link_result = runner.invoke(app, ["task", "link-email", str(task_id), str(email_id), "--type", "follow_up"])
    assert link_result.exit_code == 0
    assert 'type="follow_up"' in link_result.output

    dup_result = runner.invoke(app, ["task", "link-email", str(task_id), str(email_id)])
    assert dup_result.exit_code != 0
    assert "already linked" in dup_result.output


def test_task_show_displays_linked_email_metadata(tmp_path, monkeypatch) -> None:
    runner = _init_db(tmp_path, monkeypatch)
    email_id = _seed_email(
        external_id="<mail-show@example.com>",
        subject="Show me",
        sender="bob@example.com",
        received_at="2026-02-21T10:00:00+00:00",
    )

    task_result = runner.invoke(
        app,
        ["task", "capture", "Inspect link", "--estimate", "30", "--priority", "P2", "--status", "NEXT"],
    )
    assert task_result.exit_code == 0

    with Session(get_engine(ensure_directory=True)) as session:
        task = session.exec(select(Task).where(Task.title == "Inspect link")).one()
        task_id = task.id

    link_result = runner.invoke(app, ["task", "link-email", str(task_id), str(email_id), "--type", "reference"])
    assert link_result.exit_code == 0

    show_result = runner.invoke(app, ["task", "show", str(task_id)])
    assert show_result.exit_code == 0
    assert "Linked emails:" in show_result.output
    assert "Show me" in show_result.output
    assert "bob@example.com" in show_result.output
    assert "2026-02-21T10:00:00+00:00" in show_result.output
