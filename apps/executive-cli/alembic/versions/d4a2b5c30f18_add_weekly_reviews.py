"""add weekly reviews

Revision ID: d4a2b5c30f18
Revises: c3f1a9b20e47
Create Date: 2026-02-14 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a2b5c30f18'
down_revision: Union[str, Sequence[str], None] = 'c3f1a9b20e47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('weekly_reviews',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('week', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.Column('body_md', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('week', name='uq_weekly_reviews_week')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('weekly_reviews')
