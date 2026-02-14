from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlmodel import Session, delete, select

from executive_cli.busy_service import merge_busy_blocks
from executive_cli.db import DEFAULT_SETTINGS, PRIMARY_CALENDAR_SLUG
from executive_cli.models import BusyBlock, Calendar, DayPlan, Settings, Task, TaskPriority, TaskStatus, TimeBlock
from executive_cli.timeutil import dt_to_db, parse_time_hhmm

VALID_VARIANTS: tuple[str, ...] = ("minimal", "realistic", "aggressive")

_PRIORITY_BASE_SCORE: dict[TaskPriority, int] = {
    TaskPriority.P1: 30,
    TaskPriority.P2: 20,
    TaskPriority.P3: 10,
}
_PRIORITY_SORT_ORDER: dict[TaskPriority, int] = {
    TaskPriority.P1: 0,
    TaskPriority.P2: 1,
    TaskPriority.P3: 2,
}
_TASK_STATUS_ORDER: dict[TaskStatus, int] = {
    TaskStatus.NOW: 0,
    TaskStatus.NEXT: 1,
}


@dataclass(frozen=True)
class PlannerSettings:
    timezone_name: str
    timezone: ZoneInfo
    planning_start: time
    planning_end: time
    lunch_start: time
    lunch_duration_min: int
    buffer_min: int
    min_focus_block_min: int


@dataclass(frozen=True)
class VariantCaps:
    max_blocks: int
    max_focus_minutes: int


@dataclass
class RankedTask:
    task: Task
    score: int


@dataclass
class ScheduledBlock:
    start_dt: datetime
    end_dt: datetime
    type: str
    label: str
    task_id: int | None = None


@dataclass(frozen=True)
class DayPlanResult:
    plan_date: date
    variant: str
    timezone_name: str
    timezone: ZoneInfo
    blocks: list[ScheduledBlock]
    selected_tasks: list["SelectedTaskSummary"]
    lunch_skipped: bool


@dataclass(frozen=True)
class SelectedTaskSummary:
    id: int
    title: str
    priority: TaskPriority
    due_date: date | None


@dataclass(frozen=True)
class _Gap:
    start_dt: datetime
    end_dt: datetime
    left_block: ScheduledBlock | None
    right_block: ScheduledBlock | None


@dataclass
class _TaskState:
    ranked_task: RankedTask
    remaining_min: int
    part_index: int = 0


_VARIANT_CAPS: dict[str, VariantCaps] = {
    "minimal": VariantCaps(max_blocks=2, max_focus_minutes=120),
    "realistic": VariantCaps(max_blocks=4, max_focus_minutes=240),
    "aggressive": VariantCaps(max_blocks=10_000, max_focus_minutes=360),
}


def build_and_persist_day_plan(session: Session, *, plan_date: date, variant: str) -> DayPlanResult:
    normalized_variant = variant.strip().lower()
    if normalized_variant not in VALID_VARIANTS:
        raise ValueError("Invalid --variant. Expected one of: minimal, realistic, aggressive.")

    settings = load_planner_settings(session)
    planning_start_dt = datetime.combine(plan_date, settings.planning_start, tzinfo=settings.timezone)
    planning_end_dt = datetime.combine(plan_date, settings.planning_end, tzinfo=settings.timezone)
    if planning_start_dt >= planning_end_dt:
        raise ValueError("Invalid settings: planning_start must be earlier than planning_end.")

    ranked_tasks = _rank_tasks(_load_candidate_tasks(session), plan_date)
    busy_blocks = _load_busy_blocks(
        session=session,
        plan_date=plan_date,
        timezone=settings.timezone,
        planning_start_dt=planning_start_dt,
        planning_end_dt=planning_end_dt,
    )

    lunch_block = _place_lunch_block(
        planning_start_dt=planning_start_dt,
        planning_end_dt=planning_end_dt,
        busy_blocks=busy_blocks,
        plan_date=plan_date,
        settings=settings,
    )
    lunch_skipped = lunch_block is None and settings.lunch_duration_min > 0

    fixed_blocks: list[ScheduledBlock] = sorted(
        [*busy_blocks, *([lunch_block] if lunch_block is not None else [])],
        key=_block_sort_key,
    )
    focus_blocks, selected_tasks = _schedule_focus_blocks(
        planning_start_dt=planning_start_dt,
        planning_end_dt=planning_end_dt,
        fixed_blocks=fixed_blocks,
        ranked_tasks=ranked_tasks,
        settings=settings,
        caps=_VARIANT_CAPS[normalized_variant],
    )

    all_blocks = sorted([*fixed_blocks, *focus_blocks], key=_block_sort_key)
    _replace_day_plan(session, plan_date=plan_date, variant=normalized_variant, blocks=all_blocks)

    return DayPlanResult(
        plan_date=plan_date,
        variant=normalized_variant,
        timezone_name=settings.timezone_name,
        timezone=settings.timezone,
        blocks=all_blocks,
        selected_tasks=selected_tasks,
        lunch_skipped=lunch_skipped,
    )


def load_planner_settings(session: Session) -> PlannerSettings:
    settings_rows = session.exec(select(Settings)).all()
    raw_settings = {row.key: row.value for row in settings_rows}

    timezone_name = raw_settings.get("timezone", DEFAULT_SETTINGS["timezone"])
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid timezone setting: {timezone_name}") from exc

    planning_start = _parse_setting_time(raw_settings, "planning_start")
    planning_end = _parse_setting_time(raw_settings, "planning_end")
    lunch_start = _parse_setting_time(raw_settings, "lunch_start")
    lunch_duration_min = _parse_setting_int(raw_settings, "lunch_duration_min", minimum=0)
    buffer_min = _parse_setting_int(raw_settings, "buffer_min", minimum=0)
    min_focus_block_min = _parse_setting_int(raw_settings, "min_focus_block_min", minimum=1)

    return PlannerSettings(
        timezone_name=timezone_name,
        timezone=timezone,
        planning_start=planning_start,
        planning_end=planning_end,
        lunch_start=lunch_start,
        lunch_duration_min=lunch_duration_min,
        buffer_min=buffer_min,
        min_focus_block_min=min_focus_block_min,
    )


def _parse_setting_time(raw_settings: dict[str, str], key: str) -> time:
    value = raw_settings.get(key, DEFAULT_SETTINGS[key])
    try:
        return parse_time_hhmm(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {key} setting '{value}'. Expected HH:MM.") from exc


def _parse_setting_int(raw_settings: dict[str, str], key: str, *, minimum: int) -> int:
    value = raw_settings.get(key, DEFAULT_SETTINGS[key])
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {key} setting '{value}'. Expected integer.") from exc
    if parsed < minimum:
        raise ValueError(f"Invalid {key} setting '{value}'. Expected >= {minimum}.")
    return parsed


def _load_candidate_tasks(session: Session) -> list[Task]:
    rows = session.exec(
        select(Task).where(Task.status.in_([TaskStatus.NOW, TaskStatus.NEXT]))
    ).all()
    return sorted(
        rows,
        key=lambda task: (
            _TASK_STATUS_ORDER.get(TaskStatus(task.status), 99),
            task.id if task.id is not None else 2**31 - 1,
        ),
    )


def _rank_tasks(tasks: list[Task], plan_date: date) -> list[RankedTask]:
    ranked = [RankedTask(task=task, score=_score_task(task, plan_date)) for task in tasks]
    ranked.sort(
        key=lambda ranked_task: (
            -ranked_task.score,
            1 if ranked_task.task.due_date is None else 0,
            ranked_task.task.due_date or date.max,
            _PRIORITY_SORT_ORDER[TaskPriority(ranked_task.task.priority)],
            ranked_task.task.id if ranked_task.task.id is not None else 2**31 - 1,
        )
    )
    return ranked


def _score_task(task: Task, plan_date: date) -> int:
    score = _PRIORITY_BASE_SCORE[TaskPriority(task.priority)]
    if task.due_date is not None and task.due_date < plan_date:
        score += 15
    if task.due_date is not None and plan_date <= task.due_date <= plan_date + timedelta(days=3):
        score += 5
    if task.commitment_id is not None:
        score += 10
    return score


def _load_busy_blocks(
    *,
    session: Session,
    plan_date: date,
    timezone: ZoneInfo,
    planning_start_dt: datetime,
    planning_end_dt: datetime,
) -> list[ScheduledBlock]:
    calendar = session.exec(select(Calendar).where(Calendar.slug == PRIMARY_CALENDAR_SLUG)).first()
    if calendar is None:
        raise ValueError("Primary calendar is not initialized. Run 'execas init' first.")

    day_start = datetime.combine(plan_date, time.min, tzinfo=timezone)
    day_end = day_start + timedelta(days=1)
    busy_rows = session.exec(
        select(BusyBlock)
        .where(BusyBlock.calendar_id == calendar.id)
        .where(BusyBlock.end_dt > dt_to_db(day_start))
        .where(BusyBlock.start_dt < dt_to_db(day_end))
        .order_by(BusyBlock.start_dt, BusyBlock.id)
    ).all()

    merged = merge_busy_blocks(busy_rows)
    scheduled_busy: list[ScheduledBlock] = []
    for item in merged:
        start_dt = max(item.start_dt.astimezone(timezone), planning_start_dt)
        end_dt = min(item.end_dt.astimezone(timezone), planning_end_dt)
        if start_dt >= end_dt:
            continue
        scheduled_busy.append(
            ScheduledBlock(
                start_dt=start_dt,
                end_dt=end_dt,
                type="busy",
                label=item.title,
                task_id=None,
            )
        )
    return sorted(scheduled_busy, key=_block_sort_key)


def _place_lunch_block(
    *,
    planning_start_dt: datetime,
    planning_end_dt: datetime,
    busy_blocks: list[ScheduledBlock],
    plan_date: date,
    settings: PlannerSettings,
) -> ScheduledBlock | None:
    if settings.lunch_duration_min <= 0:
        return None

    target_start = datetime.combine(plan_date, settings.lunch_start, tzinfo=settings.timezone)
    lunch_duration = timedelta(minutes=settings.lunch_duration_min)
    gaps = _find_gaps(planning_start_dt, planning_end_dt, busy_blocks)

    candidates: list[tuple[int, datetime]] = []
    for gap in gaps:
        usable_start, usable_end = _apply_buffer_to_gap(gap, settings.buffer_min)
        latest_start = usable_end - lunch_duration
        if latest_start < usable_start:
            continue
        candidate_start = _clamp_datetime(target_start, lower=usable_start, upper=latest_start)
        distance_minutes = _abs_minutes(candidate_start - target_start)
        candidates.append((distance_minutes, candidate_start))

    if not candidates:
        return None

    _, chosen_start = min(candidates, key=lambda candidate: (candidate[0], candidate[1]))
    return ScheduledBlock(
        start_dt=chosen_start,
        end_dt=chosen_start + lunch_duration,
        type="lunch",
        label="Lunch",
        task_id=None,
    )


def _schedule_focus_blocks(
    *,
    planning_start_dt: datetime,
    planning_end_dt: datetime,
    fixed_blocks: list[ScheduledBlock],
    ranked_tasks: list[RankedTask],
    settings: PlannerSettings,
    caps: VariantCaps,
) -> tuple[list[ScheduledBlock], list[SelectedTaskSummary]]:
    task_states = [
        _TaskState(ranked_task=ranked_task, remaining_min=ranked_task.task.estimate_min)
        for ranked_task in ranked_tasks
        if ranked_task.task.estimate_min >= settings.min_focus_block_min
    ]
    if not task_states:
        return [], []

    total_focus_minutes = 0
    total_focus_blocks = 0
    selected_task_ids: set[int] = set()
    selected_tasks: list[SelectedTaskSummary] = []
    focus_blocks: list[ScheduledBlock] = []
    buffer_delta = timedelta(minutes=settings.buffer_min)

    for gap in _find_gaps(planning_start_dt, planning_end_dt, fixed_blocks):
        usable_start, usable_end = _apply_buffer_to_gap(gap, settings.buffer_min)
        cursor = usable_start

        while True:
            if total_focus_blocks >= caps.max_blocks or total_focus_minutes >= caps.max_focus_minutes:
                return focus_blocks, selected_tasks

            remaining_window_minutes = _minutes_between(cursor, usable_end)
            if remaining_window_minutes < settings.min_focus_block_min:
                break

            remaining_variant_minutes = caps.max_focus_minutes - total_focus_minutes
            if remaining_variant_minutes < settings.min_focus_block_min:
                return focus_blocks, selected_tasks

            task_state = _pick_next_task(task_states, settings.min_focus_block_min)
            if task_state is None:
                return focus_blocks, selected_tasks

            block_minutes = min(
                task_state.remaining_min,
                remaining_window_minutes,
                remaining_variant_minutes,
            )
            if block_minutes < settings.min_focus_block_min:
                task_state.remaining_min = 0
                continue

            block_start = cursor
            block_end = block_start + timedelta(minutes=block_minutes)

            task_state.part_index += 1
            is_split = task_state.remaining_min > block_minutes or task_state.part_index > 1
            if is_split:
                label = f"{task_state.ranked_task.task.title} (part {task_state.part_index})"
            else:
                label = task_state.ranked_task.task.title

            focus_blocks.append(
                ScheduledBlock(
                    start_dt=block_start,
                    end_dt=block_end,
                    type="focus",
                    label=label,
                    task_id=task_state.ranked_task.task.id,
                )
            )

            task_state.remaining_min -= block_minutes
            total_focus_minutes += block_minutes
            total_focus_blocks += 1

            task_id = task_state.ranked_task.task.id
            if task_id is not None and task_id not in selected_task_ids:
                selected_task_ids.add(task_id)
                selected_tasks.append(
                    SelectedTaskSummary(
                        id=task_id,
                        title=task_state.ranked_task.task.title,
                        priority=TaskPriority(task_state.ranked_task.task.priority),
                        due_date=task_state.ranked_task.task.due_date,
                    )
                )

            next_cursor = block_end + buffer_delta
            if next_cursor > usable_end:
                break
            cursor = next_cursor

    return focus_blocks, selected_tasks


def _pick_next_task(task_states: list[_TaskState], min_focus_block_min: int) -> _TaskState | None:
    for task_state in task_states:
        if task_state.remaining_min >= min_focus_block_min:
            return task_state
    return None


def _find_gaps(
    window_start_dt: datetime,
    window_end_dt: datetime,
    occupied_blocks: list[ScheduledBlock],
) -> list[_Gap]:
    gaps: list[_Gap] = []
    cursor = window_start_dt
    left_block: ScheduledBlock | None = None

    for block in sorted(occupied_blocks, key=_block_sort_key):
        if block.end_dt <= window_start_dt or block.start_dt >= window_end_dt:
            continue

        block_start = max(block.start_dt, window_start_dt)
        block_end = min(block.end_dt, window_end_dt)
        if block_start > cursor:
            gaps.append(
                _Gap(
                    start_dt=cursor,
                    end_dt=block_start,
                    left_block=left_block,
                    right_block=block,
                )
            )

        if block_end > cursor:
            cursor = block_end
            left_block = block

    if cursor < window_end_dt:
        gaps.append(
            _Gap(
                start_dt=cursor,
                end_dt=window_end_dt,
                left_block=left_block,
                right_block=None,
            )
        )

    return gaps


def _apply_buffer_to_gap(gap: _Gap, buffer_min: int) -> tuple[datetime, datetime]:
    if buffer_min <= 0:
        return gap.start_dt, gap.end_dt

    buffer_delta = timedelta(minutes=buffer_min)
    start_dt = gap.start_dt + (buffer_delta if gap.left_block is not None else timedelta())
    end_dt = gap.end_dt - (buffer_delta if gap.right_block is not None else timedelta())
    if end_dt < start_dt:
        return start_dt, start_dt
    return start_dt, end_dt


def _replace_day_plan(
    session: Session,
    *,
    plan_date: date,
    variant: str,
    blocks: list[ScheduledBlock],
) -> None:
    existing = session.exec(
        select(DayPlan).where(DayPlan.date == plan_date).where(DayPlan.variant == variant)
    ).first()
    if existing is not None and existing.id is not None:
        session.exec(delete(TimeBlock).where(TimeBlock.day_plan_id == existing.id))
        session.delete(existing)
        session.flush()

    day_plan = DayPlan(date=plan_date, variant=variant, source="planner")
    session.add(day_plan)
    session.flush()

    if day_plan.id is None:
        raise ValueError("Failed to create day plan row.")

    for block in blocks:
        session.add(
            TimeBlock(
                day_plan_id=day_plan.id,
                start_dt=dt_to_db(block.start_dt),
                end_dt=dt_to_db(block.end_dt),
                type=block.type,
                task_id=block.task_id,
                label=block.label,
            )
        )

    session.commit()


def _minutes_between(start_dt: datetime, end_dt: datetime) -> int:
    return int((end_dt - start_dt).total_seconds() // 60)


def _abs_minutes(delta: timedelta) -> int:
    return int(abs(delta.total_seconds()) // 60)


def _clamp_datetime(value: datetime, *, lower: datetime, upper: datetime) -> datetime:
    if value < lower:
        return lower
    if value > upper:
        return upper
    return value


def _block_sort_key(block: ScheduledBlock) -> tuple[datetime, datetime, str, str]:
    return (block.start_dt, block.end_dt, block.type, block.label)
