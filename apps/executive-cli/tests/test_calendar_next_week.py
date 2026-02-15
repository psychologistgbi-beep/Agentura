from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select
from typer.testing import CliRunner

from executive_cli.cli import app
from executive_cli.db import PRIMARY_CALENDAR_SLUG, get_engine
from executive_cli.models import BusyBlock, Calendar
from executive_cli.sync_service import CALDAV_SOURCE
from executive_cli.timeutil import MOSCOW_TZ, dt_to_db


def test_calendar_next_week_lists_only_selected_source_for_next_week(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "calendar_next_week.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    runner = CliRunner()

    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0

    with Session(get_engine(ensure_directory=True)) as session:
        calendar = session.exec(select(Calendar).where(Calendar.slug == PRIMARY_CALENDAR_SLUG)).one()
        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt=dt_to_db(datetime(2026, 2, 16, 10, 0, tzinfo=MOSCOW_TZ)),
                end_dt=dt_to_db(datetime(2026, 2, 16, 11, 0, tzinfo=MOSCOW_TZ)),
                title="Yandex sync meeting",
                source=CALDAV_SOURCE,
                external_id="uid-1",
            )
        )
        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt=dt_to_db(datetime(2026, 2, 17, 12, 0, tzinfo=MOSCOW_TZ)),
                end_dt=dt_to_db(datetime(2026, 2, 17, 13, 0, tzinfo=MOSCOW_TZ)),
                title="Manual meeting",
                source="manual",
            )
        )
        session.add(
            BusyBlock(
                calendar_id=calendar.id,
                start_dt=dt_to_db(datetime(2026, 2, 24, 9, 0, tzinfo=MOSCOW_TZ)),
                end_dt=dt_to_db(datetime(2026, 2, 24, 10, 0, tzinfo=MOSCOW_TZ)),
                title="Outside range",
                source=CALDAV_SOURCE,
                external_id="uid-2",
            )
        )
        session.commit()

    result = runner.invoke(
        app,
        ["calendar", "next-week", "--anchor-date", "2026-02-15"],
    )
    assert result.exit_code == 0
    assert "2026-02-16..2026-02-22" in result.output
    assert "Count: 1" in result.output
    assert "Yandex sync meeting" in result.output
    assert "Manual meeting" not in result.output
    assert "Outside range" not in result.output


def test_calendar_next_week_validates_non_empty_source(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "calendar_next_week_empty_source.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    runner = CliRunner()
    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0

    result = runner.invoke(app, ["calendar", "next-week", "--source", "   "])
    assert result.exit_code != 0
    assert "--source must not be empty." in result.output
