from __future__ import annotations

from datetime import datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from typer.testing import CliRunner

from executive_cli.cli import app
from executive_cli.connectors.caldav import CalendarConnectorError, CalendarSyncBatch, RemoteCalendarEvent
from executive_cli.db import PRIMARY_CALENDAR_SLUG, get_engine
from executive_cli.models import BusyBlock, Calendar, SyncState
from executive_cli.sync_service import CALDAV_SCOPE_PRIMARY, CALDAV_SOURCE, sync_calendar_primary
from executive_cli.timeutil import MOSCOW_TZ, dt_to_db


def _create_engine(tmp_path):
    db_path = tmp_path / "calendar_sync.sqlite"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_primary_calendar(session: Session) -> Calendar:
    calendar = Calendar(slug=PRIMARY_CALENDAR_SLUG, name="Primary", timezone="Europe/Moscow")
    session.add(calendar)
    session.commit()
    session.refresh(calendar)
    return calendar


def _event(
    *,
    external_id: str,
    start_h: int,
    end_h: int,
    etag: str,
    title: str,
    modified: str = "2026-02-20T06:00:00+00:00",
) -> RemoteCalendarEvent:
    return RemoteCalendarEvent(
        external_id=external_id,
        start_dt=datetime(2026, 2, 20, start_h, 0, tzinfo=MOSCOW_TZ),
        end_dt=datetime(2026, 2, 20, end_h, 0, tzinfo=MOSCOW_TZ),
        title=title,
        external_etag=etag,
        external_modified_at=modified,
    )


class FakeConnector:
    def __init__(self, batch: CalendarSyncBatch):
        self.batch = batch
        self.calls: list[tuple[str, str | None, str | None, str]] = []

    def fetch_events(
        self,
        *,
        calendar_slug: str,
        cursor: str | None,
        cursor_kind: str | None,
        timezone_name: str,
    ) -> CalendarSyncBatch:
        self.calls.append((calendar_slug, cursor, cursor_kind, timezone_name))
        return self.batch


def test_sync_service_performs_incremental_upsert_and_advances_cursor(tmp_path) -> None:
    engine = _create_engine(tmp_path)

    with Session(engine) as session:
        calendar = _seed_primary_calendar(session)
        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt=dt_to_db(datetime(2026, 2, 20, 9, 0, tzinfo=MOSCOW_TZ)),
                end_dt=dt_to_db(datetime(2026, 2, 20, 10, 0, tzinfo=MOSCOW_TZ)),
                title="Old title",
                source=CALDAV_SOURCE,
                external_id="uid-1",
                external_etag="etag-old",
                external_modified_at="2026-02-20T05:00:00+00:00",
            )
        )
        session.add(
            SyncState(
                source=CALDAV_SOURCE,
                scope=CALDAV_SCOPE_PRIMARY,
                cursor="ctag-1",
                cursor_kind="ctag",
                updated_at="2026-02-20T05:00:00+00:00",
            )
        )
        session.commit()

        connector = FakeConnector(
            CalendarSyncBatch(
                events=[
                    _event(external_id="uid-1", start_h=11, end_h=12, etag="etag-new", title="Updated title"),
                    _event(external_id="uid-2", start_h=13, end_h=14, etag="etag-2", title="New event"),
                ],
                cursor="ctag-2",
                cursor_kind="ctag",
                full_snapshot=True,
            )
        )
        result = sync_calendar_primary(session, connector=connector)

    assert connector.calls == [("primary", "ctag-1", "ctag", "Europe/Moscow")]
    assert result.inserted == 1
    assert result.updated == 1
    assert result.skipped == 0
    assert result.soft_deleted == 0
    assert result.cursor == "ctag-2"

    with Session(engine) as session:
        rows = session.exec(
            select(BusyBlock)
            .where(BusyBlock.source == CALDAV_SOURCE)
            .order_by(BusyBlock.external_id)
        ).all()
        assert [row.external_id for row in rows] == ["uid-1", "uid-2"]
        assert rows[0].title == "Updated title"
        assert rows[0].external_etag == "etag-new"
        assert rows[1].title == "New event"

        state = session.exec(
            select(SyncState)
            .where(SyncState.source == CALDAV_SOURCE)
            .where(SyncState.scope == CALDAV_SCOPE_PRIMARY)
        ).one()
        assert state.cursor == "ctag-2"
        assert state.cursor_kind == "ctag"


def test_sync_service_etag_guard_skips_unchanged_rows(tmp_path) -> None:
    engine = _create_engine(tmp_path)

    with Session(engine) as session:
        calendar = _seed_primary_calendar(session)
        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt=dt_to_db(datetime(2026, 2, 20, 9, 0, tzinfo=MOSCOW_TZ)),
                end_dt=dt_to_db(datetime(2026, 2, 20, 10, 0, tzinfo=MOSCOW_TZ)),
                title="Stable event",
                source=CALDAV_SOURCE,
                external_id="uid-1",
                external_etag="etag-1",
                external_modified_at="2026-02-20T05:00:00+00:00",
            )
        )
        session.commit()

        connector = FakeConnector(
            CalendarSyncBatch(
                events=[_event(external_id="uid-1", start_h=13, end_h=14, etag="etag-1", title="Changed title")],
                cursor="ctag-2",
                cursor_kind="ctag",
                full_snapshot=True,
            )
        )
        result = sync_calendar_primary(session, connector=connector)
        assert result.skipped == 1
        assert result.updated == 0
        assert result.inserted == 0

    with Session(engine) as session:
        row = session.exec(
            select(BusyBlock)
            .where(BusyBlock.source == CALDAV_SOURCE)
            .where(BusyBlock.external_id == "uid-1")
        ).one()
        assert row.title == "Stable event"
        assert row.start_dt == dt_to_db(datetime(2026, 2, 20, 9, 0, tzinfo=MOSCOW_TZ))
        assert row.end_dt == dt_to_db(datetime(2026, 2, 20, 10, 0, tzinfo=MOSCOW_TZ))


def test_sync_service_soft_deletes_missing_remote_and_keeps_manual_rows(tmp_path) -> None:
    engine = _create_engine(tmp_path)

    with Session(engine) as session:
        calendar = _seed_primary_calendar(session)
        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt=dt_to_db(datetime(2026, 2, 20, 9, 0, tzinfo=MOSCOW_TZ)),
                end_dt=dt_to_db(datetime(2026, 2, 20, 10, 0, tzinfo=MOSCOW_TZ)),
                title="Keep synced",
                source=CALDAV_SOURCE,
                external_id="uid-keep",
                external_etag="etag-1",
            )
        )
        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt=dt_to_db(datetime(2026, 2, 20, 11, 0, tzinfo=MOSCOW_TZ)),
                end_dt=dt_to_db(datetime(2026, 2, 20, 12, 0, tzinfo=MOSCOW_TZ)),
                title="Drop synced",
                source=CALDAV_SOURCE,
                external_id="uid-drop",
                external_etag="etag-2",
            )
        )
        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt=dt_to_db(datetime(2026, 2, 20, 13, 0, tzinfo=MOSCOW_TZ)),
                end_dt=dt_to_db(datetime(2026, 2, 20, 14, 0, tzinfo=MOSCOW_TZ)),
                title="Manual block",
                source="manual",
            )
        )
        session.commit()

        connector = FakeConnector(
            CalendarSyncBatch(
                events=[_event(external_id="uid-keep", start_h=9, end_h=10, etag="etag-1", title="Keep synced")],
                cursor="ctag-9",
                cursor_kind="ctag",
                full_snapshot=True,
            )
        )
        result = sync_calendar_primary(session, connector=connector)
        assert result.soft_deleted == 1

    with Session(engine) as session:
        keep = session.exec(
            select(BusyBlock)
            .where(BusyBlock.source == CALDAV_SOURCE)
            .where(BusyBlock.external_id == "uid-keep")
        ).one()
        drop = session.exec(
            select(BusyBlock)
            .where(BusyBlock.source == CALDAV_SOURCE)
            .where(BusyBlock.external_id == "uid-drop")
        ).one()
        manual = session.exec(select(BusyBlock).where(BusyBlock.source == "manual")).one()

        assert keep.is_deleted == 0
        assert drop.is_deleted == 1
        assert manual.is_deleted == 0


def test_sync_service_does_not_advance_cursor_on_failure(tmp_path) -> None:
    engine = _create_engine(tmp_path)

    with Session(engine) as session:
        _seed_primary_calendar(session)
        session.add(
            SyncState(
                source=CALDAV_SOURCE,
                scope=CALDAV_SCOPE_PRIMARY,
                cursor="ctag-1",
                cursor_kind="ctag",
                updated_at="2026-02-20T05:00:00+00:00",
            )
        )
        session.commit()

        bad_event = RemoteCalendarEvent(
            external_id="uid-bad",
            start_dt=datetime(2026, 2, 20, 15, 0, tzinfo=MOSCOW_TZ),
            end_dt=datetime(2026, 2, 20, 14, 0, tzinfo=MOSCOW_TZ),
            title="Broken",
            external_etag="etag-bad",
            external_modified_at="2026-02-20T06:00:00+00:00",
        )
        connector = FakeConnector(
            CalendarSyncBatch(
                events=[bad_event],
                cursor="ctag-2",
                cursor_kind="ctag",
                full_snapshot=True,
            )
        )

        with pytest.raises(ValueError):
            sync_calendar_primary(session, connector=connector)

    with Session(engine) as session:
        state = session.exec(
            select(SyncState)
            .where(SyncState.source == CALDAV_SOURCE)
            .where(SyncState.scope == CALDAV_SCOPE_PRIMARY)
        ).one()
        assert state.cursor == "ctag-1"
        assert state.cursor_kind == "ctag"


def test_busy_list_excludes_soft_deleted_rows(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "cli_busy.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    runner = CliRunner()

    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0

    with Session(get_engine(ensure_directory=True)) as session:
        calendar = session.exec(select(Calendar).where(Calendar.slug == PRIMARY_CALENDAR_SLUG)).one()
        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt="2026-02-20T09:00:00+03:00",
                end_dt="2026-02-20T10:00:00+03:00",
                title="Visible block",
                source="manual",
                is_deleted=0,
            )
        )
        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt="2026-02-20T11:00:00+03:00",
                end_dt="2026-02-20T12:00:00+03:00",
                title="Hidden block",
                source=CALDAV_SOURCE,
                external_id="uid-hidden",
                is_deleted=1,
            )
        )
        session.commit()

    list_result = runner.invoke(app, ["busy", "list", "--date", "2026-02-20"])
    assert list_result.exit_code == 0
    assert "Visible block" in list_result.output
    assert "Hidden block" not in list_result.output


def test_calendar_sync_command_shows_fallback_on_connector_error(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "calendar_cli.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    runner = CliRunner()

    def _raise_from_env(cls):
        raise CalendarConnectorError("CalDAV endpoint is unreachable.")

    monkeypatch.setattr("executive_cli.cli.CalDavConnector.from_env", classmethod(_raise_from_env))

    result = runner.invoke(app, ["calendar", "sync"])
    assert result.exit_code == 1
    assert "Calendar sync failed" in result.output
    assert "Fallback" in result.output
    assert "busy add" in result.output


def test_calendar_sync_command_executes_real_sync_flow(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "calendar_cli_success.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    runner = CliRunner()
    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0

    connector = FakeConnector(
        CalendarSyncBatch(
            events=[_event(external_id="uid-1", start_h=10, end_h=11, etag="etag-1", title="Synced meeting")],
            cursor="ctag-10",
            cursor_kind="ctag",
            full_snapshot=True,
        )
    )

    monkeypatch.setattr(
        "executive_cli.cli.CalDavConnector.from_env",
        classmethod(lambda cls: connector),
    )

    result = runner.invoke(app, ["calendar", "sync"])
    assert result.exit_code == 0
    assert "inserted=1" in result.output
    assert "cursor=ctag-10" in result.output

    with Session(get_engine(ensure_directory=True)) as session:
        synced_rows = session.exec(select(BusyBlock).where(BusyBlock.source == CALDAV_SOURCE)).all()
        assert len(synced_rows) == 1
        assert synced_rows[0].external_id == "uid-1"

        state = session.exec(
            select(SyncState)
            .where(SyncState.source == CALDAV_SOURCE)
            .where(SyncState.scope == CALDAV_SCOPE_PRIMARY)
        ).one()
        assert state.cursor == "ctag-10"

