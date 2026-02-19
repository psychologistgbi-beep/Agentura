"""Approval Gate — human-in-the-loop action blocker (ADR-12).

Any side-effect action can be queued for approval. The gate blocks pipeline
execution until the user approves or rejects the request.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from executive_cli.models import ApprovalRequest, TaskPriority, TaskStatus
from executive_cli.task_service import create_task_record


class ApprovalError(Exception):
    """Raised for approval gate errors."""


def request_approval(
    session: Session,
    *,
    pipeline_run_id: int | None,
    step_name: str | None,
    action_type: str,
    action_payload: dict[str, Any],
    context: dict[str, Any] | None = None,
    now_iso: str | None = None,
) -> int:
    """Create a pending approval request. Returns the request id."""
    now = now_iso or datetime.now(timezone.utc).isoformat()

    req = ApprovalRequest(
        pipeline_run_id=pipeline_run_id,
        step_name=step_name,
        action_type=action_type,
        action_payload_json=json.dumps(action_payload, ensure_ascii=False, default=str),
        context_json=json.dumps(context, ensure_ascii=False, default=str) if context else None,
        status="pending",
        created_at=now,
    )
    session.add(req)
    session.flush()
    return req.id  # type: ignore[return-value]


def approve(
    session: Session,
    *,
    request_id: int,
    now_iso: str | None = None,
) -> ApprovalRequest:
    """Approve a pending request. Raises if not pending."""
    now = now_iso or datetime.now(timezone.utc).isoformat()

    req = session.get(ApprovalRequest, request_id)
    if req is None:
        raise ApprovalError(f"Approval request {request_id} not found")
    if req.status != "pending":
        raise ApprovalError(f"Request {request_id} is '{req.status}', expected 'pending'")

    req.status = "approved"
    req.decided_at = now
    session.add(req)
    session.flush()
    return req


def reject(
    session: Session,
    *,
    request_id: int,
    now_iso: str | None = None,
) -> ApprovalRequest:
    """Reject a pending request. Raises if not pending."""
    now = now_iso or datetime.now(timezone.utc).isoformat()

    req = session.get(ApprovalRequest, request_id)
    if req is None:
        raise ApprovalError(f"Approval request {request_id} not found")
    if req.status != "pending":
        raise ApprovalError(f"Request {request_id} is '{req.status}', expected 'pending'")

    req.status = "rejected"
    req.decided_at = now
    session.add(req)
    session.flush()
    return req


def list_pending(session: Session) -> list[ApprovalRequest]:
    """Return all pending approval requests, oldest first."""
    return list(
        session.exec(
            select(ApprovalRequest)
            .where(ApprovalRequest.status == "pending")
            .order_by(ApprovalRequest.created_at)
        ).all()
    )


def execute_approved(
    session: Session,
    *,
    request_id: int,
    now_iso: str | None = None,
) -> Any:
    """Execute the action of an approved request. Dispatches by action_type."""
    now = now_iso or datetime.now(timezone.utc).isoformat()

    req = session.get(ApprovalRequest, request_id)
    if req is None:
        raise ApprovalError(f"Approval request {request_id} not found")
    if req.status != "approved":
        raise ApprovalError(f"Request {request_id} is '{req.status}', expected 'approved'")

    payload = json.loads(req.action_payload_json)

    if req.action_type == "create_task":
        return _execute_create_task(session, payload=payload, now_iso=now)

    if req.action_type == "add_busy_block":
        return _execute_add_busy_block(session, payload=payload, now_iso=now)

    raise ApprovalError(f"Unknown action_type: {req.action_type}")


def approve_and_execute(
    session: Session,
    *,
    request_id: int,
    now_iso: str | None = None,
) -> Any:
    """Approve and immediately execute in one call."""
    approve(session, request_id=request_id, now_iso=now_iso)
    return execute_approved(session, request_id=request_id, now_iso=now_iso)


# --- Action dispatchers ---


def _execute_create_task(
    session: Session,
    *,
    payload: dict[str, Any],
    now_iso: str,
) -> Any:
    """Create a task from approval payload."""
    from datetime import date as date_type

    due_date = None
    if payload.get("due_date"):
        due_date = date_type.fromisoformat(payload["due_date"])

    status = TaskStatus(payload.get("status", "NEXT"))
    priority = TaskPriority(payload.get("priority", "P2"))

    task = create_task_record(
        session,
        title=payload["title"],
        status=status,
        priority=priority,
        estimate_min=int(payload.get("estimate_min", 30)),
        due_date=due_date,
        area_id=payload.get("area_id"),
        project_id=payload.get("project_id"),
        commitment_id=payload.get("commitment_id"),
        waiting_on=payload.get("waiting_on"),
        ping_at=payload.get("ping_at"),
        from_email_id=payload.get("from_email_id"),
        now_iso=now_iso,
    )
    return task

def _execute_add_busy_block(
    session: Session,
    *,
    payload: dict[str, Any],
    now_iso: str,
) -> Any:
    """Create a BusyBlock from approval payload.

    Expected payload keys:
        start_dt   — ISO datetime string for block start
        end_dt     — ISO datetime string for block end
        title      — optional label
        calendar_id — calendar FK (required)
        source     — optional, defaults to "manual"
    """
    from executive_cli.models import BusyBlock

    block = BusyBlock(
        calendar_id=int(payload["calendar_id"]),
        start_dt=payload["start_dt"],
        end_dt=payload["end_dt"],
        title=payload.get("title"),
        source=payload.get("source", "manual"),
        external_id=payload.get("external_id"),
    )
    session.add(block)
    session.flush()
    return block
