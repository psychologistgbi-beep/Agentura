from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine, select

from executive_cli.models import BusyBlock, Calendar, Email, SyncState, Task, TaskEmailLink, TaskPriority, TaskStatus


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _migrated_engine(tmp_path, monkeypatch):
    db_path = tmp_path / "provenance.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    command.upgrade(cfg, "head")

    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )


def _create_calendar(session: Session, *, slug: str = "primary") -> Calendar:
    calendar = Calendar(slug=slug, name=slug.title(), timezone="Europe/Moscow")
    session.add(calendar)
    session.commit()
    session.refresh(calendar)
    return calendar


def test_provenance_tables_and_busy_block_columns_present(tmp_path, monkeypatch) -> None:
    engine = _migrated_engine(tmp_path, monkeypatch)
    inspector = sa.inspect(engine)

    table_names = set(inspector.get_table_names())
    assert "sync_state" in table_names
    assert "emails" in table_names
    assert "task_email_links" in table_names

    busy_columns = {column["name"] for column in inspector.get_columns("busy_blocks")}
    assert "source" in busy_columns
    assert "external_id" in busy_columns
    assert "external_etag" in busy_columns
    assert "external_modified_at" in busy_columns
    assert "is_deleted" in busy_columns

    with engine.connect() as conn:
        index_sql = conn.execute(
            sa.text(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type='index' AND name='uq_busy_blocks_source_external_id'
                """
            )
        ).scalar_one()
    assert "WHERE external_id IS NOT NULL" in index_sql


def test_busy_blocks_defaults_and_partial_unique_dedup(tmp_path, monkeypatch) -> None:
    engine = _migrated_engine(tmp_path, monkeypatch)

    with Session(engine) as session:
        calendar = _create_calendar(session)

        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt="2026-02-20T09:00:00+03:00",
                end_dt="2026-02-20T10:00:00+03:00",
                title="Manual 1",
            )
        )
        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt="2026-02-20T10:00:00+03:00",
                end_dt="2026-02-20T11:00:00+03:00",
                title="Manual 2",
            )
        )
        session.commit()

        manual_blocks = session.exec(select(BusyBlock).order_by(BusyBlock.id)).all()
        assert len(manual_blocks) == 2
        assert all(block.source == "manual" for block in manual_blocks)
        assert all(block.external_id is None for block in manual_blocks)
        assert all(block.is_deleted == 0 for block in manual_blocks)

        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt="2026-02-20T11:00:00+03:00",
                end_dt="2026-02-20T12:00:00+03:00",
                title="Synced",
                source="yandex_caldav",
                external_id="uid-1",
            )
        )
        session.commit()

        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt="2026-02-20T12:00:00+03:00",
                end_dt="2026-02-20T13:00:00+03:00",
                title="Duplicate synced",
                source="yandex_caldav",
                external_id="uid-1",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt="2026-02-20T13:00:00+03:00",
                end_dt="2026-02-20T14:00:00+03:00",
                title="Same external, different source",
                source="other_calendar",
                external_id="uid-1",
            )
        )
        session.commit()


def test_soft_delete_flag_semantics(tmp_path, monkeypatch) -> None:
    engine = _migrated_engine(tmp_path, monkeypatch)

    with Session(engine) as session:
        calendar = _create_calendar(session)
        block = BusyBlock(
            calendar_id=calendar.id,
            start_dt="2026-02-20T10:00:00+03:00",
            end_dt="2026-02-20T11:00:00+03:00",
            title="To soft-delete",
        )
        session.add(block)
        session.commit()
        session.refresh(block)
        assert block.is_deleted == 0

        block.is_deleted = 1
        session.add(block)
        session.commit()

        active = session.exec(select(BusyBlock).where(BusyBlock.is_deleted == 0)).all()
        deleted = session.exec(select(BusyBlock).where(BusyBlock.is_deleted == 1)).all()
        assert len(active) == 0
        assert len(deleted) == 1
        assert deleted[0].id == block.id


def test_sync_state_emails_and_task_email_links_uniqueness(tmp_path, monkeypatch) -> None:
    engine = _migrated_engine(tmp_path, monkeypatch)

    with Session(engine) as session:
        session.add(
            SyncState(
                source="yandex_caldav",
                scope="primary",
                cursor="ctag-1",
                cursor_kind="ctag",
                updated_at="2026-02-20T07:00:00+00:00",
            )
        )
        session.commit()

        session.add(
            SyncState(
                source="yandex_caldav",
                scope="primary",
                cursor="ctag-2",
                cursor_kind="ctag",
                updated_at="2026-02-20T08:00:00+00:00",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        email = Email(
            source="yandex_imap",
            external_id="<message-1@example.com>",
            mailbox_uid=123,
            subject="Subject",
            sender="alice@example.com",
            received_at="2026-02-20T09:00:00+00:00",
            first_seen_at="2026-02-20T09:00:00+00:00",
            last_seen_at="2026-02-20T09:00:00+00:00",
            flags_json='["\\\\Seen"]',
        )
        session.add(email)
        session.commit()
        session.refresh(email)

        session.add(
            Email(
                source="yandex_imap",
                external_id="<message-1@example.com>",
                mailbox_uid=124,
                first_seen_at="2026-02-20T10:00:00+00:00",
                last_seen_at="2026-02-20T10:00:00+00:00",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        task = Task(
            title="Task with email",
            status=TaskStatus.NOW,
            priority=TaskPriority.P1,
            estimate_min=30,
        )
        session.add(task)
        session.commit()
        session.refresh(task)

        session.add(
            TaskEmailLink(
                task_id=task.id,
                email_id=email.id,
                link_type="origin",
                created_at="2026-02-20T09:30:00+00:00",
            )
        )
        session.commit()

        session.add(
            TaskEmailLink(
                task_id=task.id,
                email_id=email.id,
                link_type="reference",
                created_at="2026-02-20T09:40:00+00:00",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
