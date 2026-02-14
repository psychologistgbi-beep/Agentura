"""add people decisions with fts5

Revision ID: c3f1a9b20e47
Revises: b8ada07e8d01
Create Date: 2026-02-14 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f1a9b20e47'
down_revision: Union[str, Sequence[str], None] = 'b8ada07e8d01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- people ---
    op.create_table('people',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('role', sa.Text(), nullable=True),
    sa.Column('context', sa.Text(), nullable=True),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_people_name'), 'people', ['name'], unique=False)

    # --- decisions ---
    op.create_table('decisions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('decided_date', sa.Date(), nullable=True),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )

    # --- FTS5 virtual tables (content-less external content) ---
    op.execute(
        "CREATE VIRTUAL TABLE people_fts USING fts5("
        "name, role, context, "
        "content='people', content_rowid='id'"
        ")"
    )
    op.execute(
        "CREATE VIRTUAL TABLE decisions_fts USING fts5("
        "title, body, "
        "content='decisions', content_rowid='id'"
        ")"
    )

    # --- Triggers: people ---
    op.execute(
        "CREATE TRIGGER people_ai AFTER INSERT ON people BEGIN "
        "INSERT INTO people_fts(rowid, name, role, context) "
        "VALUES (new.id, new.name, new.role, new.context); "
        "END;"
    )
    op.execute(
        "CREATE TRIGGER people_ad AFTER DELETE ON people BEGIN "
        "INSERT INTO people_fts(people_fts, rowid, name, role, context) "
        "VALUES ('delete', old.id, old.name, old.role, old.context); "
        "END;"
    )
    op.execute(
        "CREATE TRIGGER people_au AFTER UPDATE ON people BEGIN "
        "INSERT INTO people_fts(people_fts, rowid, name, role, context) "
        "VALUES ('delete', old.id, old.name, old.role, old.context); "
        "INSERT INTO people_fts(rowid, name, role, context) "
        "VALUES (new.id, new.name, new.role, new.context); "
        "END;"
    )

    # --- Triggers: decisions ---
    op.execute(
        "CREATE TRIGGER decisions_ai AFTER INSERT ON decisions BEGIN "
        "INSERT INTO decisions_fts(rowid, title, body) "
        "VALUES (new.id, new.title, new.body); "
        "END;"
    )
    op.execute(
        "CREATE TRIGGER decisions_ad AFTER DELETE ON decisions BEGIN "
        "INSERT INTO decisions_fts(decisions_fts, rowid, title, body) "
        "VALUES ('delete', old.id, old.title, old.body); "
        "END;"
    )
    op.execute(
        "CREATE TRIGGER decisions_au AFTER UPDATE ON decisions BEGIN "
        "INSERT INTO decisions_fts(decisions_fts, rowid, title, body) "
        "VALUES ('delete', old.id, old.title, old.body); "
        "INSERT INTO decisions_fts(rowid, title, body) "
        "VALUES (new.id, new.title, new.body); "
        "END;"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS decisions_au")
    op.execute("DROP TRIGGER IF EXISTS decisions_ad")
    op.execute("DROP TRIGGER IF EXISTS decisions_ai")
    op.execute("DROP TRIGGER IF EXISTS people_au")
    op.execute("DROP TRIGGER IF EXISTS people_ad")
    op.execute("DROP TRIGGER IF EXISTS people_ai")
    op.execute("DROP TABLE IF EXISTS decisions_fts")
    op.execute("DROP TABLE IF EXISTS people_fts")
    op.drop_table('decisions')
    op.drop_index(op.f('ix_people_name'), table_name='people')
    op.drop_table('people')
