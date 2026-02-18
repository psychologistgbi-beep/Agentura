"""Tests for Approval Gate (ADR-12)."""
from __future__ import annotations

import json

import pytest
from sqlmodel import Session, create_engine, SQLModel

from executive_cli.models import ApprovalRequest, Task
from executive_cli.approval_gate import (
    ApprovalError,
    approve,
    approve_and_execute,
    list_pending,
    reject,
    request_approval,
)


@pytest.fixture()
def session():
    """In-memory SQLite session with all tables."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


NOW = "2026-02-17T12:00:00+00:00"


def test_request_approval_creates_pending(session):
    req_id = request_approval(
        session,
        pipeline_run_id=None,
        step_name="test_step",
        action_type="create_task",
        action_payload={"title": "Test task", "status": "NEXT", "priority": "P2", "estimate_min": 30},
        context={"reason": "low confidence"},
        now_iso=NOW,
    )
    assert req_id is not None

    req = session.get(ApprovalRequest, req_id)
    assert req.status == "pending"
    assert req.action_type == "create_task"
    payload = json.loads(req.action_payload_json)
    assert payload["title"] == "Test task"


def test_list_pending_returns_only_pending(session):
    request_approval(
        session, pipeline_run_id=None, step_name=None,
        action_type="create_task",
        action_payload={"title": "Pending"},
        now_iso=NOW,
    )
    req_id2 = request_approval(
        session, pipeline_run_id=None, step_name=None,
        action_type="create_task",
        action_payload={"title": "Will reject"},
        now_iso=NOW,
    )
    reject(session, request_id=req_id2, now_iso=NOW)

    pending = list_pending(session)
    assert len(pending) == 1
    assert json.loads(pending[0].action_payload_json)["title"] == "Pending"


def test_approve_sets_status(session):
    req_id = request_approval(
        session, pipeline_run_id=None, step_name=None,
        action_type="create_task",
        action_payload={"title": "Approve me"},
        now_iso=NOW,
    )
    result = approve(session, request_id=req_id, now_iso=NOW)
    assert result.status == "approved"
    assert result.decided_at == NOW


def test_reject_sets_status(session):
    req_id = request_approval(
        session, pipeline_run_id=None, step_name=None,
        action_type="create_task",
        action_payload={"title": "Reject me"},
        now_iso=NOW,
    )
    result = reject(session, request_id=req_id, now_iso=NOW)
    assert result.status == "rejected"


def test_double_approve_raises(session):
    req_id = request_approval(
        session, pipeline_run_id=None, step_name=None,
        action_type="create_task",
        action_payload={"title": "Double"},
        now_iso=NOW,
    )
    approve(session, request_id=req_id, now_iso=NOW)
    with pytest.raises(ApprovalError, match="approved"):
        approve(session, request_id=req_id, now_iso=NOW)


def test_approve_not_found_raises(session):
    with pytest.raises(ApprovalError, match="not found"):
        approve(session, request_id=9999, now_iso=NOW)


def test_approve_and_execute_creates_task(session):
    req_id = request_approval(
        session, pipeline_run_id=None, step_name=None,
        action_type="create_task",
        action_payload={
            "title": "Auto task",
            "status": "NEXT",
            "priority": "P2",
            "estimate_min": 30,
        },
        now_iso=NOW,
    )
    result = approve_and_execute(session, request_id=req_id, now_iso=NOW)
    assert hasattr(result, "id")
    assert result.title == "Auto task"

    # Verify task in DB
    task = session.get(Task, result.id)
    assert task is not None
    assert task.title == "Auto task"


def test_execute_unknown_action_type_raises(session):
    req_id = request_approval(
        session, pipeline_run_id=None, step_name=None,
        action_type="send_message",
        action_payload={"to": "someone"},
        now_iso=NOW,
    )
    approve(session, request_id=req_id, now_iso=NOW)
    with pytest.raises(ApprovalError, match="Unknown action_type"):
        from executive_cli.approval_gate import execute_approved
        execute_approved(session, request_id=req_id, now_iso=NOW)


def test_execute_add_busy_block(session):
    """Approving an add_busy_block request should create a BusyBlock row."""
    from executive_cli.models import BusyBlock, Calendar

    # Need a Calendar row because BusyBlock has a FK to calendars
    calendar = Calendar(
        slug="primary",
        name="Primary",
        timezone="UTC",
    )
    session.add(calendar)
    session.flush()

    req_id = request_approval(
        session,
        pipeline_run_id=None,
        step_name="plan_day",
        action_type="add_busy_block",
        action_payload={
            "calendar_id": calendar.id,
            "start_dt": "2026-02-18T09:00:00",
            "end_dt": "2026-02-18T10:00:00",
            "title": "Morning standup",
            "source": "manual",
        },
        now_iso=NOW,
    )
    result = approve_and_execute(session, request_id=req_id, now_iso=NOW)
    assert result is not None
    assert result.title == "Morning standup"
    assert result.start_dt == "2026-02-18T09:00:00"
    assert result.end_dt == "2026-02-18T10:00:00"

    # Verify persisted in DB
    block = session.get(BusyBlock, result.id)
    assert block is not None
    assert block.calendar_id == calendar.id
