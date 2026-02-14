from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlmodel import Session, select

from executive_cli.models import (
    Area,
    Commitment,
    Project,
    Task,
    TaskPriority,
    TaskStatus,
    WeeklyReview,
)
from executive_cli.timeutil import MOSCOW_TZ, db_to_dt, dt_to_db

_WEEK_RE = re.compile(r"^\d{4}-W(0[1-9]|[1-4]\d|5[0-3])$")

# --- Scoring constants ---

_PRIORITY_BASE: dict[TaskPriority, int] = {
    TaskPriority.P1: 100,
    TaskPriority.P2: 60,
    TaskPriority.P3: 30,
}

_STATUS_WEIGHT: dict[TaskStatus, int] = {
    TaskStatus.NOW: 10,
    TaskStatus.WAITING: 5,
    TaskStatus.NEXT: 0,
}

_PRIORITY_SORT: dict[TaskPriority, int] = {
    TaskPriority.P1: 0,
    TaskPriority.P2: 1,
    TaskPriority.P3: 2,
}


def validate_week(value: str) -> str:
    """Validate YYYY-Www format strictly. Returns the validated string."""
    if not _WEEK_RE.fullmatch(value):
        raise ValueError(f"Invalid week format: {value!r}. Expected YYYY-Www (e.g. 2026-W07).")
    return value


@dataclass(frozen=True)
class ScoredTask:
    task: Task
    score: int
    reasons: list[str]


def score_task(task: Task, today: date) -> ScoredTask:
    """Score a single task deterministically. Returns ScoredTask."""
    score = _PRIORITY_BASE.get(TaskPriority(task.priority), 0)
    reasons: list[str] = []

    if TaskPriority(task.priority) == TaskPriority.P1:
        reasons.append("high_priority")

    # Due urgency
    if task.due_date is not None:
        if task.due_date < today:
            score += 80
            reasons.append("overdue")
        elif task.due_date <= today + timedelta(days=7):
            score += 40
            reasons.append("due_soon")

    # Commitment link
    if task.commitment_id is not None:
        score += 50
        reasons.append("commitment_linked")

    # Waiting urgency (ping_at within 7 days)
    if TaskStatus(task.status) == TaskStatus.WAITING and task.ping_at:
        try:
            ping_dt = db_to_dt(task.ping_at)
            now_dt = datetime.now(timezone.utc)
            if ping_dt <= now_dt + timedelta(days=7):
                score += 20
        except (ValueError, TypeError):
            pass

    # Status weight
    score += _STATUS_WEIGHT.get(TaskStatus(task.status), 0)

    return ScoredTask(task=task, score=score, reasons=reasons)


def _sort_key(st: ScoredTask) -> tuple:
    """Deterministic sort key: score desc, due_date asc (nulls last), priority asc, id asc."""
    t = st.task
    due_sort = (0, t.due_date.isoformat()) if t.due_date else (1, "")
    return (
        -st.score,
        due_sort,
        _PRIORITY_SORT.get(TaskPriority(t.priority), 99),
        t.id or 0,
    )


def _format_task_line(task: Task, project_name: str, area_name: str) -> str:
    due_str = task.due_date.isoformat() if task.due_date else "-"
    line = (
        f"- [{task.status}] {task.title} "
        f"({task.priority}, {task.estimate_min}m, due {due_str}, "
        f"project {project_name}, area {area_name})"
    )
    if TaskStatus(task.status) == TaskStatus.WAITING:
        wo = task.waiting_on or "-"
        if task.ping_at:
            try:
                ping_dt = db_to_dt(task.ping_at)
                pa = ping_dt.astimezone(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                pa = "-"
        else:
            pa = "-"
        line += f'; waiting_on="{wo}", ping_at={pa}'
    return line


def _resolve_names(
    session: Session, task: Task
) -> tuple[str, str]:
    """Resolve project and area names for a task."""
    project_name = "-"
    if task.project_id is not None:
        proj = session.get(Project, task.project_id)
        if proj:
            project_name = proj.name
    area_name = "-"
    if task.area_id is not None:
        area = session.get(Area, task.area_id)
        if area:
            area_name = area.name
    return project_name, area_name


def generate_weekly_review(
    session: Session,
    *,
    week: str,
    now: datetime,
    limit: int = 10,
    proposals: int = 5,
) -> str:
    """Generate deterministic weekly review markdown. Pure logic, no side effects beyond reads."""
    today = now.astimezone(MOSCOW_TZ).date()
    generated_str = now.astimezone(MOSCOW_TZ).isoformat()

    # Load tasks
    all_tasks = session.exec(select(Task)).all()
    now_tasks = [t for t in all_tasks if TaskStatus(t.status) == TaskStatus.NOW]
    waiting_tasks = [t for t in all_tasks if TaskStatus(t.status) == TaskStatus.WAITING]
    next_tasks = [t for t in all_tasks if TaskStatus(t.status) == TaskStatus.NEXT]

    # Score and sort
    scored_now = sorted([score_task(t, today) for t in now_tasks], key=_sort_key)
    scored_waiting = sorted([score_task(t, today) for t in waiting_tasks], key=_sort_key)
    scored_next = sorted([score_task(t, today) for t in next_tasks], key=_sort_key)

    # Action list: NOW first, then WAITING
    action_items = scored_now + scored_waiting
    action_items = action_items[:limit]

    # Waiting pings within 7 days
    now_utc = now.astimezone(timezone.utc)
    ping_cutoff = now_utc + timedelta(days=7)
    waiting_pings: list[tuple[datetime, ScoredTask]] = []
    for st in scored_waiting:
        if st.task.ping_at:
            try:
                ping_dt = db_to_dt(st.task.ping_at)
                if ping_dt <= ping_cutoff:
                    waiting_pings.append((ping_dt, st))
            except (ValueError, TypeError):
                pass
    waiting_pings.sort(key=lambda x: (x[0].isoformat(), x[1].task.id or 0))

    # Proposals: top NEXT by score (no status weight already 0)
    proposal_items = scored_next[:proposals]

    # Commitment nudge
    commitments = session.exec(
        select(Commitment).order_by(Commitment.id)
    ).all()
    cutoff_iso = dt_to_db(now_utc - timedelta(days=7))
    off_track: list[Commitment] = []

    _DIFFICULTY_ORDER = {"D5": 0, "D4": 1, "D3": 2, "D2": 3, "D1": 4}
    for c in commitments:
        recent = [
            t for t in all_tasks
            if t.commitment_id == c.id
            and TaskStatus(t.status) != TaskStatus.CANCELED
            and t.created_at >= cutoff_iso
        ]
        if len(recent) == 0:
            off_track.append(c)
    off_track.sort(key=lambda c: (_DIFFICULTY_ORDER.get(c.difficulty, 99), c.id))
    off_track = off_track[:3]

    # --- Build markdown ---
    lines: list[str] = []

    # 1. Header
    lines.append(f"# Weekly Review — {week}")
    lines.append(f"Generated: {generated_str}")
    lines.append("")

    # 2. Action list
    lines.append("## Action list (NOW + WAITING)")
    if action_items:
        for st in action_items:
            pn, an = _resolve_names(session, st.task)
            lines.append(_format_task_line(st.task, pn, an))
    else:
        lines.append("- none")
    lines.append("")

    # 3. Waiting pings
    lines.append("## Waiting pings (next 7 days)")
    if waiting_pings:
        for ping_dt, st in waiting_pings:
            pn, an = _resolve_names(session, st.task)
            lines.append(_format_task_line(st.task, pn, an))
    else:
        lines.append("- none")
    lines.append("")

    # 4. Proposals
    lines.append("## Proposals: move NEXT → NOW")
    if proposal_items:
        for st in proposal_items:
            due_str = st.task.due_date.isoformat() if st.task.due_date else "-"
            reason_str = ", ".join(st.reasons) if st.reasons else "default"
            lines.append(
                f"- {st.task.title} ({st.task.priority}, {st.task.estimate_min}m, "
                f"due {due_str}) — because: {reason_str}"
            )
    else:
        lines.append("- none")
    lines.append("")

    # 5. Commitment nudge
    lines.append("## Commitment nudge")
    if off_track:
        for c in off_track:
            lines.append(
                f"- {c.id} {c.title} — off-track (no tasks created in last 7 days). "
                "Suggest: create 1 NOW task for next action."
            )
    else:
        lines.append("- none")

    return "\n".join(lines)


def build_and_persist_weekly_review(
    session: Session,
    *,
    week: str,
    now: datetime,
    limit: int = 10,
    proposals: int = 5,
) -> str:
    """Generate review, persist (replace on rerun), return body_md."""
    body_md = generate_weekly_review(
        session, week=week, now=now, limit=limit, proposals=proposals,
    )

    # Delete existing review for this week (replace semantics)
    existing = session.exec(
        select(WeeklyReview).where(WeeklyReview.week == week)
    ).first()
    if existing is not None:
        session.delete(existing)
        session.flush()

    review = WeeklyReview(
        week=week,
        created_at=dt_to_db(now),
        body_md=body_md,
    )
    session.add(review)
    session.commit()

    return body_md
