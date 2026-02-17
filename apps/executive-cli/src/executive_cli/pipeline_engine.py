"""Pipeline Engine — deterministic state-machine runner (ADR-12).

Provides: register, run, resume, status for named pipelines.
Each pipeline is a sequence of typed steps with retry, idempotency, and audit.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from sqlmodel import Session, select

from executive_cli.models import PipelineEvent, PipelineRun

# --- Public data types ---


@dataclass
class StepContext:
    """Context passed to every step handler."""

    run_id: int
    correlation_id: str
    step_name: str
    input_data: dict[str, Any]
    session: Session


@dataclass
class ApprovalRequestInput:
    """Request for human approval, returned by a step handler."""

    action_type: str
    action_payload: dict[str, Any]
    context: dict[str, Any] | None = None


@dataclass
class StepResult:
    """Result returned by a step handler."""

    status: str = "completed"  # completed | failed | waiting_approval
    output_data: dict[str, Any] | None = None
    error: str | None = None
    approval_request: ApprovalRequestInput | None = None


@dataclass
class StepDefinition:
    """Definition of a single pipeline step."""

    name: str
    handler: Callable[[StepContext], StepResult]
    step_type: str = "deterministic"  # deterministic | llm | approval | fan_out
    max_retries: int = 0
    backoff_seconds: float = 1.0


@dataclass
class PipelineDefinition:
    """Definition of a named pipeline."""

    name: str
    steps: list[StepDefinition] = field(default_factory=list)


@dataclass
class PipelineRunResult:
    """Result of running a pipeline."""

    run_id: int
    correlation_id: str
    status: str
    output_data: dict[str, Any] | None = None
    error: str | None = None
    pending_approval_id: int | None = None


@dataclass
class PipelineRunInfo:
    """Status information for a pipeline run."""

    run_id: int
    pipeline_name: str
    status: str
    correlation_id: str
    created_at: str
    updated_at: str
    error: str | None
    events: list[dict[str, Any]]


# --- Registry ---

_registry: dict[str, PipelineDefinition] = {}


def register_pipeline(definition: PipelineDefinition) -> None:
    """Register a named pipeline definition."""
    _registry[definition.name] = definition


def get_registered_pipelines() -> list[str]:
    """Return names of all registered pipelines."""
    return list(_registry.keys())


# --- Helpers ---


def _compute_hash(data: Any) -> str:
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _compute_idempotency_key(run_id: int, step_name: str, input_hash: str) -> str:
    raw = f"{run_id}:{step_name}:{input_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Core engine ---


def run_pipeline(
    session: Session,
    *,
    pipeline_name: str,
    input_data: dict[str, Any],
    now_iso: str | None = None,
) -> PipelineRunResult:
    """Execute a registered pipeline from the beginning."""
    if pipeline_name not in _registry:
        raise PipelineError(f"Pipeline '{pipeline_name}' not registered")

    now = now_iso or _now_iso()
    correlation_id = uuid.uuid4().hex
    input_hash = _compute_hash(input_data)

    run = PipelineRun(
        pipeline_name=pipeline_name,
        status="running",
        input_hash=input_hash,
        correlation_id=correlation_id,
        input_json=json.dumps(input_data, ensure_ascii=False, default=str),
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    session.flush()

    definition = _registry[pipeline_name]
    return _execute_steps(session, run=run, definition=definition, input_data=input_data, now_iso=now)


def resume_pipeline(
    session: Session,
    *,
    run_id: int,
    now_iso: str | None = None,
) -> PipelineRunResult:
    """Resume a pipeline that was blocked on approval."""
    run = session.get(PipelineRun, run_id)
    if run is None:
        raise PipelineError(f"Pipeline run {run_id} not found")
    if run.status not in ("waiting_approval", "failed"):
        raise PipelineError(f"Pipeline run {run_id} is '{run.status}', cannot resume")
    if run.pipeline_name not in _registry:
        raise PipelineError(f"Pipeline '{run.pipeline_name}' not registered")

    now = now_iso or _now_iso()
    run.status = "running"
    run.updated_at = now
    session.add(run)

    definition = _registry[run.pipeline_name]
    input_data = json.loads(run.input_json) if run.input_json else {}
    return _execute_steps(session, run=run, definition=definition, input_data=input_data, now_iso=now)


def get_pipeline_status(session: Session, *, run_id: int) -> PipelineRunInfo:
    """Return current status of a pipeline run with all events."""
    run = session.get(PipelineRun, run_id)
    if run is None:
        raise PipelineError(f"Pipeline run {run_id} not found")

    events = session.exec(
        select(PipelineEvent)
        .where(PipelineEvent.run_id == run_id)
        .order_by(PipelineEvent.id)
    ).all()

    return PipelineRunInfo(
        run_id=run.id,  # type: ignore[arg-type]
        pipeline_name=run.pipeline_name,
        status=run.status,
        correlation_id=run.correlation_id,
        created_at=run.created_at,
        updated_at=run.updated_at,
        error=run.error,
        events=[
            {
                "step_name": e.step_name,
                "step_type": e.step_type,
                "status": e.status,
                "attempt": e.attempt,
                "duration_ms": e.duration_ms,
                "error": e.error,
            }
            for e in events
        ],
    )


def list_pipeline_runs(
    session: Session,
    *,
    status: str | None = None,
    limit: int = 20,
) -> list[PipelineRunInfo]:
    """List recent pipeline runs."""
    query = select(PipelineRun).order_by(PipelineRun.id.desc())  # type: ignore[union-attr]
    if status:
        query = query.where(PipelineRun.status == status)
    query = query.limit(limit)

    runs = session.exec(query).all()
    result = []
    for run in runs:
        events = session.exec(
            select(PipelineEvent)
            .where(PipelineEvent.run_id == run.id)
            .order_by(PipelineEvent.id)
        ).all()
        result.append(PipelineRunInfo(
            run_id=run.id,  # type: ignore[arg-type]
            pipeline_name=run.pipeline_name,
            status=run.status,
            correlation_id=run.correlation_id,
            created_at=run.created_at,
            updated_at=run.updated_at,
            error=run.error,
            events=[
                {
                    "step_name": e.step_name,
                    "step_type": e.step_type,
                    "status": e.status,
                    "attempt": e.attempt,
                    "duration_ms": e.duration_ms,
                    "error": e.error,
                }
                for e in events
            ],
        ))
    return result


# --- Internal execution ---


def _execute_steps(
    session: Session,
    *,
    run: PipelineRun,
    definition: PipelineDefinition,
    input_data: dict[str, Any],
    now_iso: str,
) -> PipelineRunResult:
    """Execute pipeline steps sequentially with idempotency and retry."""
    current_data = dict(input_data)

    for step_def in definition.steps:
        input_hash = _compute_hash(current_data)
        idem_key = _compute_idempotency_key(run.id, step_def.name, input_hash)  # type: ignore[arg-type]

        # Check idempotency — skip if already completed
        existing = session.exec(
            select(PipelineEvent).where(PipelineEvent.idempotency_key == idem_key)
        ).first()

        if existing is not None and existing.status == "completed":
            # Already done — use cached output
            if existing.output_hash:
                # Output stored in run's output_json keyed by step name
                pass
            current_data = _load_step_output(run, step_def.name) or current_data
            continue

        if existing is not None and existing.status in ("waiting_approval", "approved"):
            if existing.status == "waiting_approval":
                # Still waiting — pipeline pauses
                return PipelineRunResult(
                    run_id=run.id,  # type: ignore[arg-type]
                    correlation_id=run.correlation_id,
                    status="waiting_approval",
                )
            # Approved — continue execution
            current_data = _load_step_output(run, step_def.name) or current_data
            continue

        if existing is not None and existing.status == "rejected":
            # Step was rejected — mark pipeline as completed with skip
            current_data = _load_step_output(run, step_def.name) or current_data
            continue

        # Execute with retry
        result = _execute_step_with_retry(
            session,
            run=run,
            step_def=step_def,
            input_data=current_data,
            input_hash=input_hash,
            idem_key=idem_key,
            existing_event=existing,
            now_iso=now_iso,
        )

        if result.status == "waiting_approval":
            run.status = "waiting_approval"
            run.updated_at = now_iso
            session.add(run)
            session.flush()

            # Create approval request
            approval_id = None
            if result.approval_request:
                from executive_cli.approval_gate import request_approval

                approval_id = request_approval(
                    session,
                    pipeline_run_id=run.id,
                    step_name=step_def.name,
                    action_type=result.approval_request.action_type,
                    action_payload=result.approval_request.action_payload,
                    context=result.approval_request.context,
                    now_iso=now_iso,
                )

            return PipelineRunResult(
                run_id=run.id,  # type: ignore[arg-type]
                correlation_id=run.correlation_id,
                status="waiting_approval",
                pending_approval_id=approval_id,
            )

        if result.status == "failed":
            run.status = "failed"
            run.error = result.error
            run.updated_at = now_iso
            session.add(run)
            session.flush()
            return PipelineRunResult(
                run_id=run.id,  # type: ignore[arg-type]
                correlation_id=run.correlation_id,
                status="failed",
                error=result.error,
            )

        # Step completed — merge output into current data
        if result.output_data:
            current_data.update(result.output_data)
            _save_step_output(run, step_def.name, result.output_data)

    # All steps completed
    run.status = "completed"
    run.output_json = json.dumps(current_data, ensure_ascii=False, default=str)
    run.updated_at = now_iso
    session.add(run)
    session.flush()

    return PipelineRunResult(
        run_id=run.id,  # type: ignore[arg-type]
        correlation_id=run.correlation_id,
        status="completed",
        output_data=current_data,
    )


def _execute_step_with_retry(
    session: Session,
    *,
    run: PipelineRun,
    step_def: StepDefinition,
    input_data: dict[str, Any],
    input_hash: str,
    idem_key: str,
    existing_event: PipelineEvent | None,
    now_iso: str,
) -> StepResult:
    """Execute a single step with retry policy."""
    max_attempts = step_def.max_retries + 1
    start_attempt = 1

    if existing_event is not None and existing_event.status in ("failed", "retrying"):
        start_attempt = existing_event.attempt + 1
        if start_attempt > max_attempts:
            return StepResult(status="failed", error=existing_event.error)

    # Create or reuse a single event row for all retry attempts
    event = existing_event
    if event is None:
        event = PipelineEvent(
            run_id=run.id,  # type: ignore[arg-type]
            step_name=step_def.name,
            step_type=step_def.step_type,
            status="running",
            input_hash=input_hash,
            idempotency_key=idem_key,
            attempt=start_attempt,
            created_at=now_iso,
        )
        session.add(event)
        session.flush()

    for attempt in range(start_attempt, max_attempts + 1):
        event.status = "running"
        event.attempt = attempt
        event.error = None
        session.add(event)
        session.flush()

        ctx = StepContext(
            run_id=run.id,  # type: ignore[arg-type]
            correlation_id=run.correlation_id,
            step_name=step_def.name,
            input_data=input_data,
            session=session,
        )

        start_time = time.monotonic()
        try:
            result = step_def.handler(ctx)
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            error_msg = f"{type(exc).__name__}: {exc}"

            if attempt < max_attempts:
                event.status = "retrying"
                event.error = error_msg
                event.duration_ms = elapsed_ms
                session.add(event)
                session.flush()
                time.sleep(step_def.backoff_seconds * (2 ** (attempt - 1)))
                continue

            event.status = "failed"
            event.error = error_msg
            event.duration_ms = elapsed_ms
            session.add(event)
            session.flush()
            return StepResult(status="failed", error=error_msg)

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        if result.status == "waiting_approval":
            event.status = "waiting_approval"
            event.duration_ms = elapsed_ms
            if result.output_data:
                event.output_hash = _compute_hash(result.output_data)
            session.add(event)
            session.flush()
            return result

        if result.status == "failed":
            if attempt < max_attempts:
                event.status = "retrying"
                event.error = result.error
                event.duration_ms = elapsed_ms
                session.add(event)
                session.flush()
                time.sleep(step_def.backoff_seconds * (2 ** (attempt - 1)))
                continue

            event.status = "failed"
            event.error = result.error
            event.duration_ms = elapsed_ms
            session.add(event)
            session.flush()
            return result

        # Success
        event.status = "completed"
        event.duration_ms = elapsed_ms
        if result.output_data:
            event.output_hash = _compute_hash(result.output_data)
        session.add(event)
        session.flush()
        return result

    # Should not reach here
    return StepResult(status="failed", error="Exhausted all retry attempts")


def _save_step_output(run: PipelineRun, step_name: str, output: dict[str, Any]) -> None:
    """Save step output into the run's output_json (keyed by step name)."""
    existing = json.loads(run.output_json) if run.output_json else {}
    existing[f"__step_{step_name}"] = output
    run.output_json = json.dumps(existing, ensure_ascii=False, default=str)


def _load_step_output(run: PipelineRun, step_name: str) -> dict[str, Any] | None:
    """Load cached step output from the run's output_json."""
    if not run.output_json:
        return None
    data = json.loads(run.output_json)
    return data.get(f"__step_{step_name}")


# --- Exceptions ---


class PipelineError(Exception):
    """Raised for pipeline execution errors."""
