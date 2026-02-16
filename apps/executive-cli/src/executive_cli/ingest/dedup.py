from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlmodel import Session, select

from executive_cli.ingest.types import DRAFT_STATUS_PENDING
from executive_cli.models import IngestLog, Task, TaskDraft, TaskEmailLink, TaskStatus


@dataclass(frozen=True)
class DedupDecision:
    skip: bool
    reason: str | None = None
    dedup_flag: str | None = None


def detect_dedup(
    session: Session,
    *,
    candidate_title: str,
    source_document_id: int | None,
    source_email_id: int | None,
) -> DedupDecision:
    normalized_title = normalize_title(candidate_title)

    active_tasks = session.exec(
        select(Task).where(Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELED]))
    ).all()
    for task in active_tasks:
        if normalize_title(task.title) == normalized_title:
            return DedupDecision(skip=True, reason=f"exact_task_match:{task.id}")

    if source_email_id is not None:
        existing_origin = session.exec(
            select(TaskEmailLink).where(
                TaskEmailLink.email_id == source_email_id,
                TaskEmailLink.link_type == "origin",
            )
        ).first()
        if existing_origin is not None:
            return DedupDecision(skip=True, reason=f"email_origin_exists:{existing_origin.task_id}")

    for task in active_tasks:
        distance = normalized_levenshtein(normalized_title, normalize_title(task.title))
        if distance < 0.2:
            return DedupDecision(skip=False, dedup_flag=f"possible_duplicate_task:{task.id}")

    pending_drafts = session.exec(
        select(TaskDraft).where(TaskDraft.status == DRAFT_STATUS_PENDING)
    ).all()
    for draft in pending_drafts:
        draft_norm = normalize_title(draft.title)
        if draft_norm == normalized_title:
            return DedupDecision(skip=True, reason=f"exact_draft_match:{draft.id}")
        if normalized_levenshtein(normalized_title, draft_norm) < 0.2:
            return DedupDecision(skip=False, dedup_flag=f"possible_duplicate_draft:{draft.id}")

    if source_document_id is not None:
        logs = session.exec(
            select(IngestLog).where(IngestLog.document_id == source_document_id)
        ).all()
        for log in logs:
            logged_title = _extract_logged_title(log.details_json)
            if not logged_title:
                continue
            logged_norm = normalize_title(logged_title)
            if logged_norm == normalized_title or normalized_levenshtein(normalized_title, logged_norm) < 0.2:
                return DedupDecision(skip=True, reason=f"document_duplicate:{log.id}")

    return DedupDecision(skip=False)


def normalize_title(value: str) -> str:
    lowered = value.lower().strip()
    lowered = re.sub(r"[^\w\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


def normalized_levenshtein(left: str, right: str) -> float:
    if left == right:
        return 0.0
    if not left or not right:
        return 1.0

    distance = _levenshtein_distance(left, right)
    return distance / max(len(left), len(right))


def _levenshtein_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (0 if left_char == right_char else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def _extract_logged_title(details_json: str | None) -> str | None:
    if not details_json:
        return None
    try:
        parsed = json.loads(details_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    title = parsed.get("title")
    if not isinstance(title, str):
        return None
    return title.strip() or None
