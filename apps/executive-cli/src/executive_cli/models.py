from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum

from sqlalchemy import CheckConstraint, Column, Enum as SQLEnum
from sqlmodel import Field, SQLModel


class TaskStatus(StrEnum):
    NOW = "NOW"
    NEXT = "NEXT"
    WAITING = "WAITING"
    SOMEDAY = "SOMEDAY"
    DONE = "DONE"
    CANCELED = "CANCELED"


class TaskPriority(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Settings(SQLModel, table=True):
    __tablename__ = "settings"

    key: str = Field(primary_key=True)
    value: str


class Calendar(SQLModel, table=True):
    __tablename__ = "calendars"

    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True)
    name: str
    timezone: str


class BusyBlock(SQLModel, table=True):
    __tablename__ = "busy_blocks"

    id: int | None = Field(default=None, primary_key=True)
    calendar_id: int = Field(foreign_key="calendars.id", index=True)
    start_dt: str
    end_dt: str
    title: str | None = None


class Area(SQLModel, table=True):
    __tablename__ = "areas"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    area_id: int | None = Field(default=None, foreign_key="areas.id")


class Commitment(SQLModel, table=True):
    __tablename__ = "commitments"

    id: str = Field(primary_key=True)
    title: str
    metric: str
    due_date: date
    difficulty: str
    notes: str | None = None


class Task(SQLModel, table=True):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("estimate_min > 0", name="ck_tasks_estimate_min_gt_0"),
        CheckConstraint(
            "status != 'WAITING' OR (waiting_on IS NOT NULL AND waiting_on != '' AND ping_at IS NOT NULL)",
            name="ck_tasks_waiting_requires_fields",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    title: str
    status: TaskStatus = Field(
        sa_column=Column(
            SQLEnum(TaskStatus, name="task_status", native_enum=False, create_constraint=True),
            nullable=False,
        )
    )
    project_id: int | None = Field(default=None, foreign_key="projects.id")
    area_id: int | None = Field(default=None, foreign_key="areas.id")
    commitment_id: str | None = Field(default=None, foreign_key="commitments.id")
    priority: TaskPriority = Field(
        sa_column=Column(
            SQLEnum(TaskPriority, name="task_priority", native_enum=False, create_constraint=True),
            nullable=False,
        )
    )
    estimate_min: int
    due_date: date | None = None
    next_action: str | None = None
    waiting_on: str | None = None
    ping_at: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
