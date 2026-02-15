"""add provenance schema for external sync

Revision ID: f0c9e7b1a2d3
Revises: d4a2b5c30f18
Create Date: 2026-02-15 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f0c9e7b1a2d3"
down_revision: Union[str, Sequence[str], None] = "d4a2b5c30f18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "busy_blocks",
        sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("'manual'")),
    )
    op.add_column("busy_blocks", sa.Column("external_id", sa.Text(), nullable=True))
    op.add_column("busy_blocks", sa.Column("external_etag", sa.Text(), nullable=True))
    op.add_column("busy_blocks", sa.Column("external_modified_at", sa.Text(), nullable=True))
    op.add_column(
        "busy_blocks",
        sa.Column("is_deleted", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )

    op.execute(
        """
        CREATE UNIQUE INDEX uq_busy_blocks_source_external_id
        ON busy_blocks (calendar_id, source, external_id)
        WHERE external_id IS NOT NULL
        """
    )

    op.create_table(
        "sync_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("cursor", sa.Text(), nullable=True),
        sa.Column("cursor_kind", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "scope", name="uq_sync_state_source_scope"),
    )
    op.create_table(
        "emails",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("mailbox_uid", sa.Integer(), nullable=True),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("sender", sa.Text(), nullable=True),
        sa.Column("received_at", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.Text(), nullable=False),
        sa.Column("last_seen_at", sa.Text(), nullable=False),
        sa.Column("flags_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_emails_source_external_id"),
    )
    op.create_table(
        "task_email_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("email_id", sa.Integer(), nullable=False),
        sa.Column("link_type", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["email_id"], ["emails.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "email_id", name="uq_task_email_links_task_id_email_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("task_email_links")
    op.drop_table("emails")
    op.drop_table("sync_state")

    op.execute("DROP INDEX uq_busy_blocks_source_external_id")

    op.execute("ALTER TABLE busy_blocks DROP COLUMN is_deleted")
    op.execute("ALTER TABLE busy_blocks DROP COLUMN external_modified_at")
    op.execute("ALTER TABLE busy_blocks DROP COLUMN external_etag")
    op.execute("ALTER TABLE busy_blocks DROP COLUMN external_id")
    op.execute("ALTER TABLE busy_blocks DROP COLUMN source")
