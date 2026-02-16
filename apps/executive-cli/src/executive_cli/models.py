from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum

from sqlalchemy import CheckConstraint, Column, Enum as SQLEnum, Index, UniqueConstraint, text
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
    __table_args__ = (
        CheckConstraint(
            "julianday(end_dt) > julianday(start_dt)",
            name="ck_busy_blocks_end_after_start",
        ),
        Index(
            "uq_busy_blocks_source_external_id",
            "calendar_id",
            "source",
            "external_id",
            unique=True,
            sqlite_where=text("external_id IS NOT NULL"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    calendar_id: int = Field(foreign_key="calendars.id", index=True)
    start_dt: str
    end_dt: str
    title: str | None = None
    source: str = Field(default="manual")
    external_id: str | None = None
    external_etag: str | None = None
    external_modified_at: str | None = None
    is_deleted: int = Field(default=0)


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


class DayPlan(SQLModel, table=True):
    __tablename__ = "day_plans"
    __table_args__ = (
        UniqueConstraint("date", "variant", name="uq_day_plans_date_variant"),
    )

    id: int | None = Field(default=None, primary_key=True)
    date: date
    variant: str  # "minimal" | "realistic" | "aggressive"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = Field(default="planner")


class TimeBlock(SQLModel, table=True):
    __tablename__ = "time_blocks"

    id: int | None = Field(default=None, primary_key=True)
    day_plan_id: int = Field(foreign_key="day_plans.id", index=True)
    start_dt: str
    end_dt: str
    type: str  # "busy" | "focus" | "lunch" | "buffer" | "admin"
    task_id: int | None = Field(default=None, foreign_key="tasks.id")
    label: str | None = None


class Person(SQLModel, table=True):
    __tablename__ = "people"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    role: str | None = None
    context: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Decision(SQLModel, table=True):
    __tablename__ = "decisions"

    id: int | None = Field(default=None, primary_key=True)
    title: str
    body: str | None = None
    decided_date: date | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class WeeklyReview(SQLModel, table=True):
    __tablename__ = "weekly_reviews"

    id: int | None = Field(default=None, primary_key=True)
    week: str = Field(unique=True)
    created_at: str
    body_md: str


class SyncState(SQLModel, table=True):
    __tablename__ = "sync_state"
    __table_args__ = (
        UniqueConstraint("source", "scope", name="uq_sync_state_source_scope"),
    )

    id: int | None = Field(default=None, primary_key=True)
    source: str
    scope: str
    cursor: str | None = None
    cursor_kind: str | None = None
    updated_at: str


class Email(SQLModel, table=True):
    __tablename__ = "emails"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_emails_source_external_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    source: str
    external_id: str
    mailbox_uid: int | None = None
    subject: str | None = None
    sender: str | None = None
    received_at: str | None = None
    first_seen_at: str
    last_seen_at: str
    flags_json: str | None = None


class TaskEmailLink(SQLModel, table=True):
    __tablename__ = "task_email_links"
    __table_args__ = (
        UniqueConstraint("task_id", "email_id", name="uq_task_email_links_task_id_email_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="tasks.id")
    email_id: int = Field(foreign_key="emails.id")
    link_type: str
    created_at: str


class IngestDocument(SQLModel, table=True):
    __tablename__ = "ingest_documents"
    __table_args__ = (
        UniqueConstraint("channel", "source_ref", name="uq_ingest_documents_channel_source_ref"),
    )

    id: int | None = Field(default=None, primary_key=True)
    channel: str
    source_ref: str
    title: str | None = None
    status: str = Field(default="pending")
    items_extracted: int | None = None
    created_at: str
    processed_at: str | None = None


class TaskDraft(SQLModel, table=True):
    __tablename__ = "task_drafts"
    __table_args__ = (
        Index("ix_task_drafts_status_confidence", "status", "confidence"),
    )

    id: int | None = Field(default=None, primary_key=True)
    title: str
    suggested_status: str
    suggested_priority: str
    estimate_min: int
    due_date: date | None = None
    waiting_on: str | None = None
    ping_at: str | None = None
    project_hint: str | None = None
    commitment_hint: str | None = None
    confidence: float
    rationale: str | None = None
    dedup_flag: str | None = None
    source_channel: str
    source_document_id: int | None = Field(default=None, foreign_key="ingest_documents.id")
    source_email_id: int | None = Field(default=None, foreign_key="emails.id")
    status: str = Field(default="pending")
    created_at: str
    reviewed_at: str | None = None


class IngestLog(SQLModel, table=True):
    __tablename__ = "ingest_log"
    __table_args__ = (
        Index("ix_ingest_log_document_id", "document_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="ingest_documents.id")
    action: str
    task_id: int | None = Field(default=None, foreign_key="tasks.id")
    draft_id: int | None = Field(default=None, foreign_key="task_drafts.id")
    confidence: float | None = None
    details_json: str | None = None
    created_at: str
