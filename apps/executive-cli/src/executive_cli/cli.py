from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone as _utc_tz
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
from executive_cli.models import (
    Area,
    BusyBlock,
    Calendar,
    Commitment,
    Project,
    Task,
    TaskPriority,
    TaskStatus,
)

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

app = typer.Typer(
    name="execas",
    help="Executive Assistant CLI.",
    no_args_is_help=True,
)
area_app = typer.Typer(help="Manage areas (reference data).")
busy_app = typer.Typer(help="Manage busy blocks in the primary calendar.")
commitment_app = typer.Typer(help="Manage year commitments.")
config_app = typer.Typer(help="Manage assistant settings.")
project_app = typer.Typer(help="Manage projects (reference data).")
task_app = typer.Typer(help="Manage GTD tasks.")
app.add_typer(area_app, name="area")
app.add_typer(busy_app, name="busy")
app.add_typer(commitment_app, name="commitment")
app.add_typer(config_app, name="config")
app.add_typer(project_app, name="project")
app.add_typer(task_app, name="task")


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


VALID_DIFFICULTIES = {"D1", "D2", "D3", "D4", "D5"}

# Seed data from TECH_SPEC §6 — MVP commitments
_SEED_COMMITMENTS: list[dict[str, str]] = [
    {
        "id": "YC-1",
        "title": "Raise >=25M RUB investments in a venture project",
        "metric": "by 31.12.2026 raised >= 25M RUB investments in a venture project where user is key initiator/founder",
        "due_date": "2026-12-31",
        "difficulty": "D3",
    },
    {
        "id": "YC-2",
        "title": "Create graphic art series and commercialize",
        "metric": "by 31.12.2026 created a series of graphic art objects and commercialized them",
        "due_date": "2026-12-31",
        "difficulty": "D5",
    },
    {
        "id": "YC-3",
        "title": "4+ weeks in English-speaking professional environment",
        "metric": "by 31.12.2026 spent >= 4 weeks in an English-speaking professional environment with recorded results in English",
        "due_date": "2026-12-31",
        "difficulty": "D4",
    },
]


# --- Area commands ---


@area_app.command("add")
def area_add(name: str = typer.Argument(..., help="Area name.")) -> None:
    """Add an area. Idempotent: returns existing record if name matches."""
    trimmed = name.strip()
    if not trimmed:
        raise typer.BadParameter("Area name must not be empty.")

    with Session(get_engine(ensure_directory=True)) as session:
        existing = session.exec(select(Area).where(Area.name == trimmed)).first()
        if existing is not None:
            typer.echo(f'id={existing.id} name="{existing.name}"')
            return

        area = Area(name=trimmed)
        session.add(area)
        session.commit()
        session.refresh(area)
        typer.echo(f'id={area.id} name="{area.name}"')


@area_app.command("list")
def area_list() -> None:
    """List all areas sorted by name."""
    with Session(get_engine(ensure_directory=True)) as session:
        areas = session.exec(select(Area).order_by(Area.name)).all()

    if not areas:
        typer.echo("No areas.")
        return

    for area in areas:
        typer.echo(f'id={area.id} name="{area.name}"')


# --- Project commands ---


@project_app.command("add")
def project_add(
    name: str = typer.Argument(..., help="Project name."),
    area_name: str | None = typer.Option(None, "--area", help="Area name to link."),
) -> None:
    """Add a project. Idempotent if same name+area; error on area conflict."""
    trimmed = name.strip()
    if not trimmed:
        raise typer.BadParameter("Project name must not be empty.")

    with Session(get_engine(ensure_directory=True)) as session:
        resolved_area_id: int | None = None
        resolved_area_name: str = "-"

        if area_name is not None:
            area = session.exec(select(Area).where(Area.name == area_name.strip())).first()
            if area is None:
                raise typer.BadParameter(f'Area "{area_name.strip()}" not found. Create it first with: execas area add "{area_name.strip()}"')
            resolved_area_id = area.id
            resolved_area_name = area.name

        existing = session.exec(select(Project).where(Project.name == trimmed)).first()
        if existing is not None:
            if existing.area_id == resolved_area_id:
                existing_area_name = "-"
                if existing.area_id is not None:
                    ea = session.get(Area, existing.area_id)
                    existing_area_name = ea.name if ea else "-"
                typer.echo(f'id={existing.id} name="{existing.name}" area="{existing_area_name}"')
                return
            raise typer.BadParameter(
                f'Project "{trimmed}" already exists with a different area (area_id={existing.area_id}). '
                "Cannot overwrite. Delete or rename first."
            )

        project = Project(name=trimmed, area_id=resolved_area_id)
        session.add(project)
        session.commit()
        session.refresh(project)
        typer.echo(f'id={project.id} name="{project.name}" area="{resolved_area_name}"')


@project_app.command("list")
def project_list() -> None:
    """List all projects sorted by name, with area info."""
    with Session(get_engine(ensure_directory=True)) as session:
        projects = session.exec(select(Project).order_by(Project.name)).all()

        if not projects:
            typer.echo("No projects.")
            return

        for proj in projects:
            area_name = "-"
            if proj.area_id is not None:
                area = session.get(Area, proj.area_id)
                if area:
                    area_name = area.name
            typer.echo(f'id={proj.id} name="{proj.name}" area="{area_name}"')


# --- Commitment commands ---


def _format_commitment(c: Commitment) -> str:
    return f'id={c.id} due={c.due_date} difficulty={c.difficulty} title="{c.title}"'


@commitment_app.command("add")
def commitment_add(
    cid: str = typer.Option(..., "--id", help="Commitment ID (e.g. YC-1)."),
    title: str = typer.Option(..., "--title", help="Commitment title."),
    metric: str = typer.Option(..., "--metric", help="Definition of done / metric."),
    due: str = typer.Option(..., "--due", help="Due date YYYY-MM-DD."),
    difficulty: str = typer.Option(..., "--difficulty", help="Difficulty D1..D5."),
    notes: str | None = typer.Option(None, "--notes", help="Optional notes."),
) -> None:
    """Add a commitment. Idempotent if all fields match; error on conflict."""
    trimmed_id = cid.strip()
    if not trimmed_id:
        raise typer.BadParameter("Commitment --id must not be empty.")

    difficulty_upper = difficulty.strip().upper()
    if difficulty_upper not in VALID_DIFFICULTIES:
        raise typer.BadParameter(f"Invalid --difficulty: {difficulty}. Must be one of: D1, D2, D3, D4, D5.")

    due_date = _parse_date(due)

    with Session(get_engine(ensure_directory=True)) as session:
        existing = session.get(Commitment, trimmed_id)
        if existing is not None:
            # Check full identity for idempotent behavior
            fields_match = (
                existing.title == title.strip()
                and existing.metric == metric.strip()
                and existing.due_date == due_date
                and existing.difficulty == difficulty_upper
                and (existing.notes or None) == (notes.strip() if notes else None)
            )
            if fields_match:
                typer.echo(_format_commitment(existing))
                return
            raise typer.BadParameter(
                f'Commitment "{trimmed_id}" already exists with different fields. '
                "Delete or update manually before re-adding."
            )

        commitment = Commitment(
            id=trimmed_id,
            title=title.strip(),
            metric=metric.strip(),
            due_date=due_date,
            difficulty=difficulty_upper,
            notes=notes.strip() if notes else None,
        )
        session.add(commitment)
        session.commit()
        session.refresh(commitment)
        typer.echo(_format_commitment(commitment))


@commitment_app.command("list")
def commitment_list() -> None:
    """List all commitments sorted by due_date then id."""
    with Session(get_engine(ensure_directory=True)) as session:
        commitments = session.exec(
            select(Commitment).order_by(Commitment.due_date, Commitment.id)
        ).all()

    if not commitments:
        typer.echo("No commitments.")
        return

    for c in commitments:
        typer.echo(_format_commitment(c))


@commitment_app.command("import")
def commitment_import() -> None:
    """Seed YC-1..YC-3 from spec. Idempotent: skip existing, warn on conflicts."""
    inserted = 0
    skipped = 0
    conflicts = 0

    with Session(get_engine(ensure_directory=True)) as session:
        for seed in _SEED_COMMITMENTS:
            existing = session.get(Commitment, seed["id"])
            if existing is not None:
                due_date = datetime.strptime(seed["due_date"], "%Y-%m-%d").date()
                fields_match = (
                    existing.title == seed["title"]
                    and existing.metric == seed["metric"]
                    and existing.due_date == due_date
                    and existing.difficulty == seed["difficulty"]
                    and existing.notes == seed.get("notes")
                )
                if fields_match:
                    skipped += 1
                else:
                    conflicts += 1
                    typer.echo(f'[yellow]CONFLICT:[/yellow] {seed["id"]} exists with different fields — skipping.', err=True)
                continue

            commitment = Commitment(
                id=seed["id"],
                title=seed["title"],
                metric=seed["metric"],
                due_date=datetime.strptime(seed["due_date"], "%Y-%m-%d").date(),
                difficulty=seed["difficulty"],
                notes=seed.get("notes"),
            )
            session.add(commitment)
            inserted += 1

        session.commit()

    typer.echo(f"imported={inserted} skipped={skipped} conflicts={conflicts}")


# --- Task commands ---

_STATUS_PRIORITY_ORDER = {s: i for i, s in enumerate(
    [TaskStatus.NOW, TaskStatus.NEXT, TaskStatus.WAITING, TaskStatus.SOMEDAY, TaskStatus.DONE, TaskStatus.CANCELED]
)}
_PRIORITY_ORDER = {p: i for i, p in enumerate([TaskPriority.P1, TaskPriority.P2, TaskPriority.P3])}


def _now_iso() -> str:
    """Current UTC time as ISO-8601 with offset (consistent with models.py default_factory)."""
    return datetime.now(_utc_tz.utc).isoformat()


def _format_task(t: Task) -> str:
    line = f'id={t.id} status={t.status} priority={t.priority} estimate={t.estimate_min} due={t.due_date or "-"} title="{t.title}"'
    if t.status == TaskStatus.WAITING:
        ping_display = t.ping_at or "-"
        line += f' waiting_on="{t.waiting_on or "-"}" ping_at="{ping_display}"'
    return line


def _resolve_area_id(session: Session, area_name: str | None) -> int | None:
    if area_name is None:
        return None
    area = session.exec(select(Area).where(Area.name == area_name.strip())).first()
    if area is None:
        raise typer.BadParameter(f'Area "{area_name.strip()}" not found.')
    return area.id


def _resolve_project_id(session: Session, project_name: str | None) -> int | None:
    if project_name is None:
        return None
    proj = session.exec(select(Project).where(Project.name == project_name.strip())).first()
    if proj is None:
        raise typer.BadParameter(f'Project "{project_name.strip()}" not found.')
    return proj.id


def _resolve_commitment_id(session: Session, commitment_id: str | None) -> str | None:
    if commitment_id is None:
        return None
    c = session.get(Commitment, commitment_id.strip())
    if c is None:
        raise typer.BadParameter(f'Commitment "{commitment_id.strip()}" not found.')
    return c.id


@task_app.command("capture")
def task_capture(
    title: str = typer.Argument(..., help="Task title."),
    estimate: int = typer.Option(..., "--estimate", help="Estimate in minutes (>0)."),
    priority: str = typer.Option(..., "--priority", help="Priority: P1, P2, or P3."),
    status: str = typer.Option("NOW", "--status", help="Initial status (NOW, NEXT, SOMEDAY)."),
    area_name: str | None = typer.Option(None, "--area", help="Area name."),
    project_name: str | None = typer.Option(None, "--project", help="Project name."),
    commitment_id: str | None = typer.Option(None, "--commitment", help="Commitment ID."),
    due: str | None = typer.Option(None, "--due", help="Due date YYYY-MM-DD."),
) -> None:
    """Capture a new task with required estimate and priority."""
    trimmed = title.strip()
    if not trimmed:
        raise typer.BadParameter("Task title must not be empty.")

    if estimate <= 0:
        raise typer.BadParameter("--estimate must be > 0.")

    priority_upper = priority.strip().upper()
    try:
        parsed_priority = TaskPriority(priority_upper)
    except ValueError:
        raise typer.BadParameter(f"Invalid --priority: {priority}. Must be P1, P2, or P3.")

    status_upper = status.strip().upper()
    allowed_capture_statuses = {TaskStatus.NOW, TaskStatus.NEXT, TaskStatus.SOMEDAY}
    try:
        parsed_status = TaskStatus(status_upper)
    except ValueError:
        raise typer.BadParameter(f"Invalid --status: {status}. Must be NOW, NEXT, or SOMEDAY.")
    if parsed_status not in allowed_capture_statuses:
        raise typer.BadParameter(f"Cannot capture with status {status_upper}. Use NOW, NEXT, or SOMEDAY.")

    due_date = _parse_date(due) if due else None

    now = _now_iso()

    with Session(get_engine(ensure_directory=True)) as session:
        area_id = _resolve_area_id(session, area_name)
        project_id = _resolve_project_id(session, project_name)
        cmt_id = _resolve_commitment_id(session, commitment_id)

        task = Task(
            title=trimmed,
            status=parsed_status,
            priority=parsed_priority,
            estimate_min=estimate,
            due_date=due_date,
            area_id=area_id,
            project_id=project_id,
            commitment_id=cmt_id,
            created_at=now,
            updated_at=now,
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        typer.echo(_format_task(task))


@task_app.command("list")
def task_list(
    status: str | None = typer.Option(None, "--status", help="Filter by status."),
    area_name: str | None = typer.Option(None, "--area", help="Filter by area name."),
    project_name: str | None = typer.Option(None, "--project", help="Filter by project name."),
    commitment_id: str | None = typer.Option(None, "--commitment", help="Filter by commitment ID."),
) -> None:
    """List tasks with optional filters, sorted by status/priority/due/id."""
    with Session(get_engine(ensure_directory=True)) as session:
        query = select(Task)

        if status is not None:
            status_upper = status.strip().upper()
            try:
                parsed_status = TaskStatus(status_upper)
            except ValueError:
                raise typer.BadParameter(f"Invalid --status: {status}.")
            query = query.where(Task.status == parsed_status)

        if area_name is not None:
            area_id = _resolve_area_id(session, area_name)
            query = query.where(Task.area_id == area_id)

        if project_name is not None:
            project_id = _resolve_project_id(session, project_name)
            query = query.where(Task.project_id == project_id)

        if commitment_id is not None:
            cmt_id = _resolve_commitment_id(session, commitment_id)
            query = query.where(Task.commitment_id == cmt_id)

        tasks = session.exec(query).all()

    if not tasks:
        typer.echo("No tasks.")
        return

    # Sort in Python: status order, priority order, due_date (nulls last), id
    def sort_key(t: Task):
        due_sort = (0, t.due_date.isoformat()) if t.due_date else (1, "")
        return (
            _STATUS_PRIORITY_ORDER.get(TaskStatus(t.status), 99),
            _PRIORITY_ORDER.get(TaskPriority(t.priority), 99),
            due_sort,
            t.id or 0,
        )

    tasks_sorted = sorted(tasks, key=sort_key)
    for t in tasks_sorted:
        typer.echo(_format_task(t))


@task_app.command("move")
def task_move(
    task_id: int = typer.Argument(..., help="Task ID."),
    status: str = typer.Option(..., "--status", help="New status."),
) -> None:
    """Change task status. Moving to WAITING requires execas task waiting instead."""
    status_upper = status.strip().upper()
    try:
        parsed_status = TaskStatus(status_upper)
    except ValueError:
        raise typer.BadParameter(f"Invalid --status: {status}. Must be one of: {', '.join(s.value for s in TaskStatus)}.")

    with Session(get_engine(ensure_directory=True)) as session:
        task = session.get(Task, task_id)
        if task is None:
            raise typer.BadParameter(f"Task {task_id} not found.")

        if parsed_status == TaskStatus.WAITING:
            if not task.waiting_on or not task.ping_at:
                raise typer.BadParameter(
                    "Cannot move to WAITING without waiting_on and ping_at. "
                    'Use: execas task waiting <id> --on "..." --ping "YYYY-MM-DD HH:MM"'
                )

        task.status = parsed_status
        task.updated_at = _now_iso()
        session.commit()
        session.refresh(task)
        typer.echo(_format_task(task))


@task_app.command("waiting")
def task_waiting(
    task_id: int = typer.Argument(..., help="Task ID."),
    on: str = typer.Option(..., "--on", help="Who or what we are waiting on."),
    ping: str = typer.Option(..., "--ping", help="Ping datetime YYYY-MM-DD HH:MM (Europe/Moscow)."),
) -> None:
    """Set task to WAITING with waiting_on and ping_at."""
    on_trimmed = on.strip()
    if not on_trimmed:
        raise typer.BadParameter("--on must not be empty.")

    try:
        naive_dt = datetime.strptime(ping.strip(), "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise typer.BadParameter("Invalid --ping format. Expected 'YYYY-MM-DD HH:MM'.") from exc

    ping_dt = naive_dt.replace(tzinfo=MOSCOW_TZ)

    with Session(get_engine(ensure_directory=True)) as session:
        task = session.get(Task, task_id)
        if task is None:
            raise typer.BadParameter(f"Task {task_id} not found.")

        task.status = TaskStatus.WAITING
        task.waiting_on = on_trimmed
        task.ping_at = ping_dt.isoformat()
        task.updated_at = _now_iso()
        session.commit()
        session.refresh(task)
        typer.echo(_format_task(task))


@task_app.command("done")
def task_done(
    task_id: int = typer.Argument(..., help="Task ID."),
) -> None:
    """Mark a task as DONE (shortcut for move --status DONE)."""
    with Session(get_engine(ensure_directory=True)) as session:
        task = session.get(Task, task_id)
        if task is None:
            raise typer.BadParameter(f"Task {task_id} not found.")

        task.status = TaskStatus.DONE
        task.updated_at = _now_iso()
        session.commit()
        session.refresh(task)
        typer.echo(_format_task(task))


def main() -> None:
    app()
