from __future__ import annotations

import json
from dataclasses import dataclass

from sqlmodel import Session

from executive_cli.ingest.dedup import DedupDecision
from executive_cli.ingest.types import DRAFT_STATUS_PENDING, ClassifiedCandidate
from executive_cli.models import IngestLog, TaskDraft
from executive_cli.task_service import TaskServiceError, create_task_record


@dataclass(frozen=True)
class RouteOutcome:
    auto_created: int = 0
    drafted: int = 0
    skipped: int = 0


def route_candidate(
    session: Session,
    *,
    candidate: ClassifiedCandidate,
    dedup: DedupDecision,
    auto_threshold: float,
    now_iso: str,
) -> RouteOutcome:
    if dedup.skip:
        _log_action(
            session,
            document_id=candidate.source_document_id,
            action="dedup_hit",
            confidence=candidate.confidence,
            now_iso=now_iso,
            details={"reason": dedup.reason, "title": candidate.title},
        )
        return RouteOutcome(skipped=1)

    if candidate.confidence < 0.3:
        _log_action(
            session,
            document_id=candidate.source_document_id,
            action="skipped",
            confidence=candidate.confidence,
            now_iso=now_iso,
            details={"reason": "low_confidence", "title": candidate.title},
        )
        return RouteOutcome(skipped=1)

    if dedup.dedup_flag or candidate.confidence < auto_threshold:
        draft = TaskDraft(
            title=candidate.title,
            suggested_status=candidate.status.value,
            suggested_priority=candidate.priority.value,
            estimate_min=candidate.estimate_min,
            due_date=candidate.due_date,
            waiting_on=candidate.waiting_on,
            ping_at=candidate.ping_at,
            project_hint=None,
            commitment_hint=candidate.commitment_id,
            confidence=candidate.confidence,
            rationale=candidate.rationale,
            dedup_flag=dedup.dedup_flag,
            source_channel=candidate.source_channel,
            source_document_id=candidate.source_document_id,
            source_email_id=candidate.source_email_id,
            status=DRAFT_STATUS_PENDING,
            created_at=now_iso,
        )
        session.add(draft)
        session.flush()
        _log_action(
            session,
            document_id=candidate.source_document_id,
            action="drafted",
            draft_id=draft.id,
            confidence=candidate.confidence,
            now_iso=now_iso,
            details={"title": candidate.title, "dedup_flag": dedup.dedup_flag},
        )
        return RouteOutcome(drafted=1)

    try:
        task = create_task_record(
            session,
            title=candidate.title,
            status=candidate.status,
            priority=candidate.priority,
            estimate_min=candidate.estimate_min,
            due_date=candidate.due_date,
            area_id=candidate.area_id,
            project_id=candidate.project_id,
            commitment_id=candidate.commitment_id,
            waiting_on=candidate.waiting_on,
            ping_at=candidate.ping_at,
            from_email_id=candidate.source_email_id,
            now_iso=now_iso,
            link_type="origin",
        )
    except TaskServiceError:
        _log_action(
            session,
            document_id=candidate.source_document_id,
            action="skipped",
            confidence=candidate.confidence,
            now_iso=now_iso,
            details={"reason": "task_service_rejected", "title": candidate.title},
        )
        return RouteOutcome(skipped=1)

    _log_action(
        session,
        document_id=candidate.source_document_id,
        action="auto_created",
        task_id=task.id,
        confidence=candidate.confidence,
        now_iso=now_iso,
        details={"title": candidate.title},
    )
    return RouteOutcome(auto_created=1)


def _log_action(
    session: Session,
    *,
    document_id: int | None,
    action: str,
    now_iso: str,
    task_id: int | None = None,
    draft_id: int | None = None,
    confidence: float | None = None,
    details: dict[str, str | None] | None = None,
) -> None:
    if document_id is None:
        return
    details_json = json.dumps(details or {}, ensure_ascii=False)
    session.add(
        IngestLog(
            document_id=document_id,
            action=action,
            task_id=task_id,
            draft_id=draft_id,
            confidence=confidence,
            details_json=details_json,
            created_at=now_iso,
        )
    )
