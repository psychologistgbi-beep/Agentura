"""Pipeline, LLM, and Approval statistics for the dashboard."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session, select

from executive_cli.models import ApprovalRequest, LLMCallLog, PipelineRun


@dataclass
class PipelineStats:
    total_runs: int = 0
    completed: int = 0
    failed: int = 0
    waiting_approval: int = 0
    by_pipeline: dict[str, int] = field(default_factory=dict)


@dataclass
class LLMStats:
    total_calls: int = 0
    ollama_calls: int = 0
    anthropic_calls: int = 0
    openai_calls: int = 0
    local_calls: int = 0
    failed_calls: int = 0
    avg_latency_ms: float | None = None
    total_tokens: int = 0


@dataclass
class ApprovalStats:
    pending: int = 0
    approved_today: int = 0
    rejected_today: int = 0


def pipeline_stats(session: Session, *, since_iso: str | None = None) -> PipelineStats:
    query = select(PipelineRun)
    if since_iso:
        query = query.where(PipelineRun.created_at >= since_iso)
    runs = session.exec(query).all()

    by_pipeline: dict[str, int] = {}
    completed = failed = waiting = 0
    for run in runs:
        by_pipeline[run.pipeline_name] = by_pipeline.get(run.pipeline_name, 0) + 1
        if run.status == "completed":
            completed += 1
        elif run.status == "failed":
            failed += 1
        elif run.status == "waiting_approval":
            waiting += 1

    return PipelineStats(
        total_runs=len(runs),
        completed=completed,
        failed=failed,
        waiting_approval=waiting,
        by_pipeline=by_pipeline,
    )


def llm_stats(session: Session, *, since_iso: str | None = None) -> LLMStats:
    query = select(LLMCallLog)
    if since_iso:
        query = query.where(LLMCallLog.created_at >= since_iso)
    calls = session.exec(query).all()

    if not calls:
        return LLMStats()

    ollama = anthropic = openai = local = failed = 0
    total_latency = 0
    latency_count = 0
    total_tokens = 0

    for call in calls:
        p = (call.provider or "").lower()
        if p == "ollama":
            ollama += 1
        elif p == "anthropic":
            anthropic += 1
        elif p == "openai":
            openai += 1
        elif p == "local":
            local += 1
        if call.status == "error":
            failed += 1
        if call.latency_ms is not None:
            total_latency += call.latency_ms
            latency_count += 1
        total_tokens += (call.prompt_tokens or 0) + (call.completion_tokens or 0)

    avg = total_latency / latency_count if latency_count else None
    return LLMStats(
        total_calls=len(calls),
        ollama_calls=ollama,
        anthropic_calls=anthropic,
        openai_calls=openai,
        local_calls=local,
        failed_calls=failed,
        avg_latency_ms=avg,
        total_tokens=total_tokens,
    )


def approval_stats(session: Session) -> ApprovalStats:
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date().isoformat()

    all_req = session.exec(select(ApprovalRequest)).all()
    pending = sum(1 for r in all_req if r.status == "pending")
    approved_today = sum(
        1 for r in all_req
        if r.status == "approved" and r.decided_at and r.decided_at[:10] == today
    )
    rejected_today = sum(
        1 for r in all_req
        if r.status == "rejected" and r.decided_at and r.decided_at[:10] == today
    )
    return ApprovalStats(
        pending=pending,
        approved_today=approved_today,
        rejected_today=rejected_today,
    )
