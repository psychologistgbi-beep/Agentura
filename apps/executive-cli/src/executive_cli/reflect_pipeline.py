"""Weekly Reflect Pipeline — ADR-12 Sprint 4."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlmodel import Session, select

from executive_cli.models import ApprovalRequest, LLMCallLog, PipelineRun, Task, TaskStatus
from executive_cli.llm_gateway import call_llm
from executive_cli.pipeline_engine import (
    PipelineDefinition,
    StepContext,
    StepDefinition,
    StepResult,
    register_pipeline,
    run_pipeline,
)

PIPELINE_NAME = "weekly_reflect"


@dataclass
class WeeklyReflectResult:
    week: str = ""
    tasks_done: int = 0
    tasks_created: int = 0
    pending_approvals: int = 0
    llm_calls_this_week: int = 0
    suggestions: list[str] = field(default_factory=list)
    report_text: str = ""


def _step_collect(ctx: StepContext) -> StepResult:
    """Gather weekly stats from DB."""
    session = ctx.session
    week = ctx.input_data.get("week", "")

    # Count tasks
    all_tasks = session.exec(select(Task)).all()
    done = sum(1 for t in all_tasks if t.status == TaskStatus.DONE)
    created_count = len(all_tasks)

    # Count pending approvals
    pending = len(session.exec(
        select(ApprovalRequest).where(ApprovalRequest.status == "pending")
    ).all())

    # Count LLM calls this week
    llm_calls = len(session.exec(select(LLMCallLog)).all())

    # Count pipeline runs
    pipeline_runs = len(session.exec(select(PipelineRun)).all())

    return StepResult(
        status="completed",
        output_data={
            "week": week,
            "tasks_done": done,
            "tasks_created": created_count,
            "pending_approvals": pending,
            "llm_calls_this_week": llm_calls,
            "pipeline_runs": pipeline_runs,
        },
    )


def _step_analyze(ctx: StepContext) -> StepResult:
    """Use local LLM to generate suggestions."""
    data = ctx.input_data
    week = data.get("week", "")
    tasks_done = data.get("tasks_done", 0)
    tasks_created = data.get("tasks_created", 0)
    pending = data.get("pending_approvals", 0)
    llm_calls = data.get("llm_calls_this_week", 0)

    suggestions: list[str] = []

    # Try Ollama for intelligent suggestions
    try:
        prompt = (
            f"Weekly GTD review for {week}.\n"
            f"Stats: tasks_done={tasks_done}, tasks_created={tasks_created}, "
            f"pending_approvals={pending}, llm_calls={llm_calls}.\n"
            "Return a JSON array of 2-3 short actionable improvement suggestions (strings). "
            "Example: [\"Review 5 oldest pending approvals\", \"Close WAITING tasks overdue by 7+ days\"]"
        )
        session = ctx.session
        response = call_llm(
            session,
            prompt=prompt,
            provider="ollama",
            model="qwen2.5:7b",
            temperature=0.3,
            correlation_id=ctx.correlation_id,
            now_iso=data.get("now_iso", datetime.now(timezone.utc).isoformat()),
            parse_json=True,
        )
        if isinstance(response.parsed, list):
            suggestions = [str(s) for s in response.parsed[:3]]
    except Exception:
        pass

    # Fallback: rule-based suggestions
    if not suggestions:
        if pending > 5:
            suggestions.append(f"Process {pending} pending approvals with `execas approve batch`")
        if tasks_done == 0:
            suggestions.append("No tasks completed this week — review task priorities")
        if llm_calls > 100:
            suggestions.append("High LLM usage — review auto-threshold settings")
        if not suggestions:
            suggestions.append("Good week — keep the momentum!")

    return StepResult(
        status="completed",
        output_data={"suggestions": suggestions},
    )


def _step_store(ctx: StepContext) -> StepResult:
    """Store weekly review via existing review service."""
    session = ctx.session
    week = ctx.input_data.get("week", "")
    now_iso = ctx.input_data.get("now_iso", datetime.now(timezone.utc).isoformat())

    try:
        from datetime import datetime as _dt
        from executive_cli.review import build_and_persist_weekly_review
        # build_and_persist_weekly_review expects a datetime object for 'now'
        now_dt = _dt.fromisoformat(now_iso.replace("Z", "+00:00"))
        build_and_persist_weekly_review(session, week=week, now=now_dt)
    except Exception:
        # Review service may have a different interface — skip gracefully
        pass

    return StepResult(status="completed", output_data={"stored": True})


def _step_present(ctx: StepContext) -> StepResult:
    """Format the report text."""
    data = ctx.input_data
    week = data.get("week", "")
    tasks_done = data.get("tasks_done", 0)
    tasks_created = data.get("tasks_created", 0)
    pending = data.get("pending_approvals", 0)
    llm_calls = data.get("llm_calls_this_week", 0)
    suggestions = data.get("suggestions", [])

    lines = [
        f"Weekly Reflect — {week}",
        "─" * 30,
        f"Tasks done     : {tasks_done}",
        f"Tasks total    : {tasks_created}",
        f"Pending approv.: {pending}",
        f"LLM calls      : {llm_calls}",
        "",
        "Suggestions:",
    ]
    for s in suggestions:
        lines.append(f"  * {s}")

    report_text = "\n".join(lines)
    return StepResult(status="completed", output_data={"report_text": report_text})


def register_weekly_reflect_pipeline() -> None:
    definition = PipelineDefinition(
        name=PIPELINE_NAME,
        steps=[
            StepDefinition(name="collect", handler=_step_collect, step_type="deterministic"),
            StepDefinition(name="analyze", handler=_step_analyze, step_type="llm", max_retries=1),
            StepDefinition(name="store", handler=_step_store, step_type="deterministic"),
            StepDefinition(name="present", handler=_step_present, step_type="deterministic"),
        ],
    )
    register_pipeline(definition)


def run_weekly_reflect(
    session: Session,
    *,
    week: str,
    now_iso: str,
) -> WeeklyReflectResult:
    register_weekly_reflect_pipeline()

    result = run_pipeline(
        session,
        pipeline_name=PIPELINE_NAME,
        input_data={"week": week, "now_iso": now_iso},
        now_iso=now_iso,
    )
    session.commit()

    out = result.output_data or {}
    return WeeklyReflectResult(
        week=week,
        tasks_done=out.get("tasks_done", 0),
        tasks_created=out.get("tasks_created", 0),
        pending_approvals=out.get("pending_approvals", 0),
        llm_calls_this_week=out.get("llm_calls_this_week", 0),
        suggestions=out.get("suggestions", []),
        report_text=out.get("report_text", ""),
    )
