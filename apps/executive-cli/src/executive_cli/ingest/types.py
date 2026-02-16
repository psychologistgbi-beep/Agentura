from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from executive_cli.models import TaskPriority, TaskStatus

CHANNEL_MEETING = "meeting_notes"
CHANNEL_DIALOGUE = "assistant_dialogue"
CHANNEL_EMAIL = "yandex_imap"

DOC_STATUS_PENDING = "pending"
DOC_STATUS_PROCESSED = "processed"
DOC_STATUS_FAILED = "failed"

DRAFT_STATUS_PENDING = "pending"
DRAFT_STATUS_ACCEPTED = "accepted"
DRAFT_STATUS_SKIPPED = "skipped"


@dataclass
class ExtractedCandidate:
    title: str
    suggested_status: str | None
    suggested_priority: str | None
    estimate_min: int | None
    due_date: str | None
    waiting_on: str | None
    ping_at: str | None
    commitment_hint: str | None
    project_hint: str | None
    confidence: float
    rationale: str | None


@dataclass
class ClassifiedCandidate:
    title: str
    status: TaskStatus
    priority: TaskPriority
    estimate_min: int
    due_date: date | None
    waiting_on: str | None
    ping_at: str | None
    commitment_id: str | None
    project_id: int | None
    area_id: int | None
    source_channel: str
    source_document_id: int | None
    source_email_id: int | None
    confidence: float
    rationale: str | None
    dedup_flag: str | None = None


@dataclass(frozen=True)
class IngestProcessSummary:
    processed_documents: int = 0
    failed_documents: int = 0
    pending_documents: int = 0
    extracted: int = 0
    auto_created: int = 0
    drafted: int = 0
    skipped: int = 0
