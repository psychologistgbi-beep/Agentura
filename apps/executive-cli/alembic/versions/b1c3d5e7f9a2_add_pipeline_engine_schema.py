"""add pipeline engine schema

Revision ID: b1c3d5e7f9a2
Revises: a7b9c2d4e6f1
Create Date: 2026-02-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1c3d5e7f9a2"
down_revision: Union[str, Sequence[str], None] = "a7b9c2d4e6f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — ADR-12: Pipeline Engine & Approval Gate."""
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pipeline_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("input_hash", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=True),
        sa.Column("output_json", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("correlation_id", name="uq_pipeline_runs_correlation_id"),
    )
    op.create_index("ix_pipeline_runs_pipeline_name", "pipeline_runs", ["pipeline_name"], unique=False)

    op.create_table(
        "pipeline_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.Text(), nullable=False),
        sa.Column("step_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("input_hash", sa.Text(), nullable=True),
        sa.Column("output_hash", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_pipeline_events_idempotency_key"),
    )
    op.create_index("ix_pipeline_events_run_id", "pipeline_events", ["run_id"], unique=False)

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("step_name", sa.Text(), nullable=True),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("action_payload_json", sa.Text(), nullable=False),
        sa.Column("context_json", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("decided_at", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.Text(), nullable=True, server_default=sa.text("'user'")),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_requests_action_type", "approval_requests", ["action_type"], unique=False)
    op.create_index("ix_approval_requests_pipeline_run_id", "approval_requests", ["pipeline_run_id"], unique=False)

    op.create_table(
        "llm_call_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.Text(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_hash", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_call_log_correlation_id", "llm_call_log", ["correlation_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_llm_call_log_correlation_id", table_name="llm_call_log")
    op.drop_table("llm_call_log")

    op.drop_index("ix_approval_requests_pipeline_run_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_action_type", table_name="approval_requests")
    op.drop_table("approval_requests")

    op.drop_index("ix_pipeline_events_run_id", table_name="pipeline_events")
    op.drop_table("pipeline_events")

    op.drop_index("ix_pipeline_runs_pipeline_name", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
