from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import typer
from rich import print
from sqlmodel import Session, select

from executive_cli.config import list_settings, upsert_setting
from executive_cli.db import (
    PRIMARY_CALENDAR_SLUG,
    get_engine,
    initialize_database,
)
from executive_cli.models import BusyBlock, Calendar

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

app = typer.Typer(
    name="execas",
    help="Executive Assistant CLI.",
    no_args_is_help=True,
)
busy_app = typer.Typer(help="Manage busy blocks in the primary calendar.")
config_app = typer.Typer(help="Manage assistant settings.")
app.add_typer(busy_app, name="busy")
app.add_typer(config_app, name="config")


@dataclass
class MergedBusyBlock:
    start_dt: datetime
    end_dt: datetime
    title_parts: list[str]

    @property
    def title(self) -> str:
        return " | ".join(self.title_parts)


def _parse_date(value: str) -> datetime.date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise typer.BadParameter("Invalid --date format. Expected YYYY-MM-DD.") from exc


def _parse_time(value: str, field_name: str) -> datetime.time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise typer.BadParameter(f"Invalid --{field_name} format. Expected HH:MM.") from exc


def _get_primary_calendar(session: Session) -> Calendar:
    calendar = session.exec(select(Calendar).where(Calendar.slug == PRIMARY_CALENDAR_SLUG)).first()
    if calendar is None:
        raise typer.BadParameter("Primary calendar is not initialized. Run 'execas init' first.")
    return calendar


def _merge_busy_blocks(rows: list[BusyBlock]) -> list[MergedBusyBlock]:
    parsed_rows = sorted(
        rows,
        key=lambda row: (
            datetime.fromisoformat(row.start_dt),
            row.id if row.id is not None else -1,
        ),
    )

    merged: list[MergedBusyBlock] = []
    for row in parsed_rows:
        start_dt = datetime.fromisoformat(row.start_dt)
        end_dt = datetime.fromisoformat(row.end_dt)
        row_title = row.title or "(untitled)"

        if not merged:
            merged.append(MergedBusyBlock(start_dt=start_dt, end_dt=end_dt, title_parts=[row_title]))
            continue

        current = merged[-1]
        if start_dt <= current.end_dt:
            if end_dt > current.end_dt:
                current.end_dt = end_dt
            current.title_parts.append(row_title)
            continue

        merged.append(MergedBusyBlock(start_dt=start_dt, end_dt=end_dt, title_parts=[row_title]))

    return merged


@app.callback()
def root() -> None:
    """Executive Assistant CLI entrypoint."""


@app.command()
def init() -> None:
    """Initialize DB, run migrations, and seed defaults."""
    db_path = initialize_database()
    print(f"[green]Initialized database:[/green] {db_path}")


@busy_app.command("add")
def busy_add(
    date_value: str = typer.Option(..., "--date", help="Date in YYYY-MM-DD (Europe/Moscow)."),
    start: str = typer.Option(..., "--start", help="Start time in HH:MM."),
    end: str = typer.Option(..., "--end", help="End time in HH:MM."),
    title: str = typer.Option(..., "--title", help="Busy block title."),
) -> None:
    """Add a busy block to the primary calendar without merging raw rows."""
    local_date = _parse_date(date_value)
    start_time = _parse_time(start, "start")
    end_time = _parse_time(end, "end")

    start_dt = datetime.combine(local_date, start_time, tzinfo=MOSCOW_TZ)
    end_dt = datetime.combine(local_date, end_time, tzinfo=MOSCOW_TZ)

    if start_dt >= end_dt:
        raise typer.BadParameter("Invalid interval: --start must be earlier than --end.")

    with Session(get_engine(ensure_directory=True)) as session:
        calendar = _get_primary_calendar(session)
        block = BusyBlock(
            calendar_id=calendar.id,
            start_dt=start_dt.isoformat(),
            end_dt=end_dt.isoformat(),
            title=title,
        )
        session.add(block)
        session.commit()

    print(
        f"[green]Added busy block:[/green] {start_dt.strftime('%H:%M')}–{end_dt.strftime('%H:%M')} | {title}"
    )


@busy_app.command("list")
def busy_list(
    date_value: str = typer.Option(..., "--date", help="Date in YYYY-MM-DD (Europe/Moscow)."),
) -> None:
    """List merged busy blocks for the given local date (merge-on-read)."""
    local_date = _parse_date(date_value)

    day_start = datetime.combine(local_date, datetime.min.time(), tzinfo=MOSCOW_TZ)
    day_end = datetime.combine(local_date, datetime.max.time(), tzinfo=MOSCOW_TZ)

    with Session(get_engine(ensure_directory=True)) as session:
        calendar = _get_primary_calendar(session)
        rows = session.exec(
            select(BusyBlock)
            .where(BusyBlock.calendar_id == calendar.id)
            .where(BusyBlock.end_dt > day_start.isoformat())
            .where(BusyBlock.start_dt < day_end.isoformat())
            .order_by(BusyBlock.start_dt, BusyBlock.id)
        ).all()

    merged = _merge_busy_blocks(rows)
    if not merged:
        print(f"[yellow]No busy blocks for {local_date.isoformat()}[/yellow]")
        return

    print(f"[bold]Busy blocks for {local_date.isoformat()} (Europe/Moscow):[/bold]")
    for item in merged:
        print(f"- {item.start_dt.strftime('%H:%M')}–{item.end_dt.strftime('%H:%M')} | {item.title}")


@config_app.command("show")
def config_show() -> None:
    """Print all settings as key=value, sorted by key."""
    with Session(get_engine(ensure_directory=True)) as session:
        settings = list_settings(session)

    for setting in settings:
        typer.echo(f"{setting.key}={setting.value}")


@config_app.command("set")
def config_set(key: str, value: str) -> None:
    """Validate and upsert a setting."""
    with Session(get_engine(ensure_directory=True)) as session:
        try:
            setting = upsert_setting(session, key=key, value=value)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"{setting.key}={setting.value}")


def main() -> None:
    app()
