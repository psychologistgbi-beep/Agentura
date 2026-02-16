from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func
from sqlmodel import Session, select

from executive_cli.db import DEFAULT_SETTINGS
from executive_cli.ingest.types import ClassifiedCandidate, ExtractedCandidate
from executive_cli.models import Commitment, Project, Settings, TaskPriority, TaskStatus
from executive_cli.timeutil import dt_to_db


def classify_candidates(
    session: Session,
    *,
    candidates: list[ExtractedCandidate],
    source_channel: str,
    source_document_id: int | None,
    source_email_id: int | None,
) -> list[ClassifiedCandidate]:
    user_tz = _get_user_timezone(session)
    now_local = datetime.now(user_tz)

    results: list[ClassifiedCandidate] = []
    for candidate in candidates:
        status = _parse_status(candidate.suggested_status)
        priority = _parse_priority(candidate.suggested_priority)
        estimate_min = candidate.estimate_min if candidate.estimate_min and candidate.estimate_min > 0 else 30
        due_date = _parse_due_date(candidate.due_date)

        project_id, area_id = _resolve_project(session, candidate.project_hint)
        commitment_id = _resolve_commitment(session, candidate.commitment_hint)

        waiting_on = (candidate.waiting_on or "").strip() or None
        ping_at = _resolve_ping_at(
            ping_raw=candidate.ping_at,
            status=status,
            waiting_on=waiting_on,
            due_date=due_date,
            now_local=now_local,
            timezone_name=user_tz.key,
        )
        if status == TaskStatus.WAITING and (not waiting_on or not ping_at):
            status = TaskStatus.NEXT
            waiting_on = None
            ping_at = None

        results.append(
            ClassifiedCandidate(
                title=candidate.title,
                status=status,
                priority=priority,
                estimate_min=estimate_min,
                due_date=due_date,
                waiting_on=waiting_on,
                ping_at=ping_at,
                commitment_id=commitment_id,
                project_id=project_id,
                area_id=area_id,
                source_channel=source_channel,
                source_document_id=source_document_id,
                source_email_id=source_email_id,
                confidence=max(0.0, min(1.0, candidate.confidence)),
                rationale=candidate.rationale,
            )
        )
    return results


def _parse_status(value: str | None) -> TaskStatus:
    if not value:
        return TaskStatus.NEXT
    try:
        return TaskStatus(value.strip().upper())
    except ValueError:
        return TaskStatus.NEXT


def _parse_priority(value: str | None) -> TaskPriority:
    if not value:
        return TaskPriority.P2
    try:
        return TaskPriority(value.strip().upper())
    except ValueError:
        return TaskPriority.P2


def _parse_due_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _resolve_project(session: Session, project_hint: str | None) -> tuple[int | None, int | None]:
    if not project_hint:
        return None, None
    normalized = project_hint.strip().lower()
    if not normalized:
        return None, None

    project = session.exec(
        select(Project).where(func.lower(Project.name) == normalized)
    ).first()
    if project is None:
        return None, None
    return project.id, project.area_id


def _resolve_commitment(session: Session, commitment_hint: str | None) -> str | None:
    if not commitment_hint:
        return None

    normalized = commitment_hint.strip()
    if not normalized:
        return None

    direct = session.get(Commitment, normalized)
    if direct is not None:
        return direct.id

    prefix_matches = session.exec(
        select(Commitment).where(Commitment.id.like(f"{normalized}%"))
    ).all()
    if len(prefix_matches) == 1:
        return prefix_matches[0].id
    return None


def _resolve_ping_at(
    *,
    ping_raw: str | None,
    status: TaskStatus,
    waiting_on: str | None,
    due_date,
    now_local: datetime,
    timezone_name: str,
) -> str | None:
    if status != TaskStatus.WAITING or not waiting_on:
        return None

    if ping_raw:
        try:
            return dt_to_db(datetime.fromisoformat(ping_raw.strip()))
        except ValueError:
            pass

    if due_date is not None:
        try:
            tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            tz = timezone.utc
        due_dt = datetime.combine(due_date, time(hour=10, minute=0), tzinfo=tz)
        return dt_to_db(due_dt)

    return dt_to_db(now_local + timedelta(days=7))


def _get_user_timezone(session: Session) -> ZoneInfo:
    setting = session.get(Settings, "timezone")
    timezone_name = setting.value if setting is not None else DEFAULT_SETTINGS["timezone"]
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")
