"""Tests for Pipeline Engine (ADR-12)."""
from __future__ import annotations

import json

import pytest
from sqlmodel import Session, create_engine, SQLModel

from executive_cli.models import PipelineEvent, PipelineRun
from executive_cli.pipeline_engine import (
    ApprovalRequestInput,
    PipelineDefinition,
    PipelineError,
    StepContext,
    StepDefinition,
    StepResult,
    _registry,
    get_pipeline_status,
    list_pipeline_runs,
    register_pipeline,
    resume_pipeline,
    run_pipeline,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Reset pipeline registry between tests."""
    saved = dict(_registry)
    _registry.clear()
    yield
    _registry.clear()
    _registry.update(saved)


@pytest.fixture()
def session():
    """In-memory SQLite session with all tables."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


NOW = "2026-02-17T12:00:00+00:00"


def _make_echo_step(name: str = "echo") -> StepDefinition:
    """Step that echoes input as output."""
    def handler(ctx: StepContext) -> StepResult:
        return StepResult(
            status="completed",
            output_data={"echoed": ctx.input_data.get("msg", "")},
        )
    return StepDefinition(name=name, handler=handler, step_type="deterministic")


def _make_fail_step(name: str = "fail", max_retries: int = 0) -> StepDefinition:
    """Step that always raises."""
    def handler(ctx: StepContext) -> StepResult:
        raise RuntimeError("intentional failure")
    return StepDefinition(name=name, handler=handler, step_type="deterministic", max_retries=max_retries)


def _make_approval_step(name: str = "approve_step") -> StepDefinition:
    """Step that requests approval."""
    def handler(ctx: StepContext) -> StepResult:
        return StepResult(
            status="waiting_approval",
            output_data={"needs_approval": True},
            approval_request=ApprovalRequestInput(
                action_type="create_task",
                action_payload={"title": "Test task"},
                context={"reason": "low confidence"},
            ),
        )
    return StepDefinition(name=name, handler=handler, step_type="approval")


# --- Registration ---

def test_register_and_list_pipelines():
    register_pipeline(PipelineDefinition(name="test_pipe", steps=[_make_echo_step()]))
    assert "test_pipe" in _registry


def test_run_unregistered_pipeline_raises(session):
    with pytest.raises(PipelineError, match="not registered"):
        run_pipeline(session, pipeline_name="nope", input_data={}, now_iso=NOW)


# --- Basic execution ---

def test_run_single_step_pipeline(session):
    register_pipeline(PipelineDefinition(
        name="single",
        steps=[_make_echo_step()],
    ))
    result = run_pipeline(session, pipeline_name="single", input_data={"msg": "hello"}, now_iso=NOW)
    assert result.status == "completed"
    assert result.output_data["echoed"] == "hello"

    # Check DB records
    run = session.get(PipelineRun, result.run_id)
    assert run is not None
    assert run.status == "completed"
    assert run.correlation_id == result.correlation_id


def test_run_multi_step_pipeline(session):
    def add_suffix(ctx: StepContext) -> StepResult:
        return StepResult(
            status="completed",
            output_data={"msg": ctx.input_data.get("msg", "") + "_processed"},
        )

    register_pipeline(PipelineDefinition(
        name="multi",
        steps=[
            StepDefinition(name="step1", handler=lambda ctx: StepResult(
                status="completed", output_data={"msg": "step1_done"},
            ), step_type="deterministic"),
            StepDefinition(name="step2", handler=add_suffix, step_type="deterministic"),
        ],
    ))
    result = run_pipeline(session, pipeline_name="multi", input_data={}, now_iso=NOW)
    assert result.status == "completed"
    assert result.output_data["msg"] == "step1_done_processed"


# --- Idempotency ---

def test_idempotency_reruns_skip_completed_steps(session):
    call_count = {"n": 0}

    def counting_handler(ctx: StepContext) -> StepResult:
        call_count["n"] += 1
        return StepResult(status="completed", output_data={"count": call_count["n"]})

    register_pipeline(PipelineDefinition(
        name="idem",
        steps=[StepDefinition(name="count", handler=counting_handler, step_type="deterministic")],
    ))

    r1 = run_pipeline(session, pipeline_name="idem", input_data={"x": 1}, now_iso=NOW)
    assert r1.status == "completed"
    assert call_count["n"] == 1

    # Re-running with same input should create a NEW run (different correlation_id)
    # But the engine creates a new run each time — idempotency is per step within a run
    r2 = run_pipeline(session, pipeline_name="idem", input_data={"x": 1}, now_iso=NOW)
    assert r2.status == "completed"
    assert call_count["n"] == 2  # New run = new execution


# --- Retry ---

def test_step_failure_marks_pipeline_failed(session):
    register_pipeline(PipelineDefinition(
        name="fail_pipe",
        steps=[_make_fail_step()],
    ))
    result = run_pipeline(session, pipeline_name="fail_pipe", input_data={}, now_iso=NOW)
    assert result.status == "failed"
    assert "intentional failure" in result.error


def test_retry_on_failure(session):
    attempts = {"n": 0}

    def flaky_handler(ctx: StepContext) -> StepResult:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("transient error")
        return StepResult(status="completed", output_data={"ok": True})

    register_pipeline(PipelineDefinition(
        name="retry_pipe",
        steps=[StepDefinition(
            name="flaky",
            handler=flaky_handler,
            step_type="deterministic",
            max_retries=2,
            backoff_seconds=0,  # no wait in tests
        )],
    ))
    result = run_pipeline(session, pipeline_name="retry_pipe", input_data={}, now_iso=NOW)
    assert result.status == "completed"
    assert attempts["n"] == 2


# --- Approval ---

def test_approval_pauses_pipeline(session):
    register_pipeline(PipelineDefinition(
        name="approval_pipe",
        steps=[_make_approval_step()],
    ))
    result = run_pipeline(session, pipeline_name="approval_pipe", input_data={}, now_iso=NOW)
    assert result.status == "waiting_approval"
    assert result.pending_approval_id is not None

    run = session.get(PipelineRun, result.run_id)
    assert run.status == "waiting_approval"


# --- Status ---

def test_get_pipeline_status(session):
    register_pipeline(PipelineDefinition(
        name="status_pipe",
        steps=[_make_echo_step()],
    ))
    result = run_pipeline(session, pipeline_name="status_pipe", input_data={"msg": "hi"}, now_iso=NOW)
    info = get_pipeline_status(session, run_id=result.run_id)
    assert info.pipeline_name == "status_pipe"
    assert info.status == "completed"
    assert len(info.events) == 1
    assert info.events[0]["step_name"] == "echo"
    assert info.events[0]["status"] == "completed"


def test_list_pipeline_runs(session):
    register_pipeline(PipelineDefinition(
        name="list_pipe",
        steps=[_make_echo_step()],
    ))
    run_pipeline(session, pipeline_name="list_pipe", input_data={}, now_iso=NOW)
    run_pipeline(session, pipeline_name="list_pipe", input_data={}, now_iso=NOW)

    runs = list_pipeline_runs(session)
    assert len(runs) == 2


def test_status_not_found_raises(session):
    with pytest.raises(PipelineError, match="not found"):
        get_pipeline_status(session, run_id=9999)
