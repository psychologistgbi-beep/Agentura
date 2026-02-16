from __future__ import annotations

from datetime import date

import sqlalchemy as sa
from sqlmodel import Session

from executive_cli.models import Email, Task, TaskEmailLink, TaskPriority, TaskStatus


class TaskServiceError(ValueError):
    """Raised when task creation fails validation or linkage invariants."""


def create_task_record(
    session: Session,
    *,
    title: str,
    status: TaskStatus,
    priority: TaskPriority,
    estimate_min: int,
    due_date: date | None,
    now_iso: str,
    area_id: int | None = None,
    project_id: int | None = None,
    commitment_id: str | None = None,
    waiting_on: str | None = None,
    ping_at: str | None = None,
    from_email_id: int | None = None,
    link_type: str = "origin",
) -> Task:
    if not title.strip():
        raise TaskServiceError("Task title must not be empty.")
    if estimate_min <= 0:
        raise TaskServiceError("Task estimate must be > 0.")

    if status == TaskStatus.WAITING:
        if not waiting_on or not waiting_on.strip() or not ping_at:
            raise TaskServiceError("WAITING task requires waiting_on and ping_at.")

    if from_email_id is not None:
        email_row = session.get(Email, from_email_id)
        if email_row is None:
            raise TaskServiceError(f"Email {from_email_id} not found.")

    task = Task(
        title=title.strip(),
        status=status,
        priority=priority,
        estimate_min=estimate_min,
        due_date=due_date,
        area_id=area_id,
        project_id=project_id,
        commitment_id=commitment_id,
        waiting_on=waiting_on.strip() if waiting_on else None,
        ping_at=ping_at,
        created_at=now_iso,
        updated_at=now_iso,
    )
    session.add(task)
    session.flush()

    if from_email_id is not None:
        session.add(
            TaskEmailLink(
                task_id=task.id,
                email_id=from_email_id,
                link_type=link_type,
                created_at=now_iso,
            )
        )
        try:
            session.flush()
        except sa.exc.IntegrityError as exc:
            session.rollback()
            raise TaskServiceError(
                f"Task {task.id} is already linked to email {from_email_id}."
            ) from exc

    return task
