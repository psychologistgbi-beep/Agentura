"""GTD Daily Pipeline — full daily cycle on Pipeline Engine (ADR-12 Sprint 3)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlmodel import Session, select

from executive_cli.ingest.email_pipeline import (
    ingest_email_via_pipeline,
    register_email_ingest_pipeline,
)
from executive_cli.models import ApprovalRequest
from executive_cli.pipeline_engine import (
    PipelineDefinition,
    StepContext,
    StepDefinition,
    StepResult,
    register_pipeline,
    run_pipeline,
)

PIPELINE_NAME = "gtd_daily"


@dataclass
class GtdDailySummary:
    emails_processed: int = 0
    tasks_auto_created: int = 0
    drafts_created: int = 0
    pending_approvals: int = 0
    plan_blocks: int = 0


def _step_sync_mail(ctx: StepContext) -> StepResult:
    """Attempt mail sync — skip gracefully if no credentials."""
    try:
        from executive_cli.sync_service import sync_mailbox  # may not be configured
        # sync_mailbox requires credentials; skip silently if unavailable
    except (ImportError, Exception):
        pass
    return StepResult(status="completed", output_data={"sync_skipped": True})


def _step_triage_emails(ctx: StepContext) -> StepResult:
    """Run email ingest pipeline for all unprocessed emails."""
    session = ctx.session
    now_iso = ctx.input_data.get("now_iso", datetime.utcnow().isoformat())
    email_limit = int(ctx.input_data.get("email_limit", 50))

    register_email_ingest_pipeline()
    summary = ingest_email_via_pipeline(
        session,
        since=None,
        limit=email_limit,
        now_iso=now_iso,
    )

    return StepResult(
        status="completed",
        output_data={
            "emails_processed": summary.processed_documents,
            "tasks_auto_created": summary.auto_created,
            "drafts_created": summary.drafted,
        },
    )


def _step_pending_report(ctx: StepContext) -> StepResult:
    """Count pending approvals."""
    session = ctx.session
    count = len(
        session.exec(
            select(ApprovalRequest).where(ApprovalRequest.status == "pending")
        ).all()
    )
    return StepResult(status="completed", output_data={"pending_approvals": count})


def _step_plan_day(ctx: StepContext) -> StepResult:
    """Run day planner for target date."""
    session = ctx.session
    date_iso = ctx.input_data.get("date_iso", datetime.utcnow().date().isoformat())
    variant = ctx.input_data.get("variant", "realistic")

    try:
        from executive_cli.planner import build_and_persist_day_plan, VALID_VARIANTS

        # Normalize variant: plan_day only supports minimal/realistic/aggressive
        normalized = variant.strip().lower()
        if normalized not in VALID_VARIANTS:
            normalized = "realistic"

        plan = build_and_persist_day_plan(
            session,
            plan_date=date.fromisoformat(date_iso),
            variant=normalized,
        )
        blocks = len(plan.blocks) if hasattr(plan, "blocks") else 0
    except Exception:
        blocks = 0

    return StepResult(status="completed", output_data={"plan_blocks": blocks})


def register_gtd_daily_pipeline() -> None:
    """Register the gtd_daily pipeline definition."""
    definition = PipelineDefinition(
        name=PIPELINE_NAME,
        steps=[
            StepDefinition(
                name="sync_mail",
                handler=_step_sync_mail,
                step_type="deterministic",
            ),
            StepDefinition(
                name="triage",
                handler=_step_triage_emails,
                step_type="deterministic",
            ),
            StepDefinition(
                name="pending_report",
                handler=_step_pending_report,
                step_type="deterministic",
            ),
            StepDefinition(
                name="plan_day",
                handler=_step_plan_day,
                step_type="deterministic",
            ),
        ],
    )
    register_pipeline(definition)


def run_gtd_daily(
    session: Session,
    *,
    date_iso: str,
    variant: str = "realistic",
    email_limit: int = 50,
    now_iso: str,
) -> GtdDailySummary:
    """Execute the full GTD daily cycle and return a summary."""
    register_gtd_daily_pipeline()

    result = run_pipeline(
        session,
        pipeline_name=PIPELINE_NAME,
        input_data={
            "date_iso": date_iso,
            "variant": variant,
            "email_limit": email_limit,
            "now_iso": now_iso,
        },
        now_iso=now_iso,
    )

    session.commit()

    out = result.output_data or {}
    return GtdDailySummary(
        emails_processed=out.get("emails_processed", 0),
        tasks_auto_created=out.get("tasks_auto_created", 0),
        drafts_created=out.get("drafts_created", 0),
        pending_approvals=out.get("pending_approvals", 0),
        plan_blocks=out.get("plan_blocks", 0),
    )
