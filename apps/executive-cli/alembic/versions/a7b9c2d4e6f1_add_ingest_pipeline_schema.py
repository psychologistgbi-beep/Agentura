"""add ingest pipeline schema

Revision ID: a7b9c2d4e6f1
Revises: f0c9e7b1a2d3
Create Date: 2026-02-16 18:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7b9c2d4e6f1"
down_revision: Union[str, Sequence[str], None] = "f0c9e7b1a2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "ingest_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("items_extracted", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("processed_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel", "source_ref", name="uq_ingest_documents_channel_source_ref"),
    )

    op.create_table(
        "task_drafts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("suggested_status", sa.Text(), nullable=False),
        sa.Column("suggested_priority", sa.Text(), nullable=False),
        sa.Column("estimate_min", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("waiting_on", sa.Text(), nullable=True),
        sa.Column("ping_at", sa.Text(), nullable=True),
        sa.Column("project_hint", sa.Text(), nullable=True),
        sa.Column("commitment_hint", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("dedup_flag", sa.Text(), nullable=True),
        sa.Column("source_channel", sa.Text(), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("source_email_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["source_document_id"], ["ingest_documents.id"]),
        sa.ForeignKeyConstraint(["source_email_id"], ["emails.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_drafts_status_confidence", "task_drafts", ["status", "confidence"], unique=False)

    op.create_table(
        "ingest_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("draft_id", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["ingest_documents.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["draft_id"], ["task_drafts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingest_log_document_id", "ingest_log", ["document_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_ingest_log_document_id", table_name="ingest_log")
    op.drop_table("ingest_log")

    op.drop_index("ix_task_drafts_status_confidence", table_name="task_drafts")
    op.drop_table("task_drafts")

    op.drop_table("ingest_documents")
