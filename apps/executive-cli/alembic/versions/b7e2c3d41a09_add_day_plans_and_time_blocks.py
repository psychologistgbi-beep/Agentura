"""add day plans and time blocks

Revision ID: b7e2c3d41a09
Revises: a06fd86f7505
Create Date: 2026-02-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2c3d41a09'
down_revision: Union[str, Sequence[str], None] = 'a06fd86f7505'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('day_plans',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('variant', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.Column('source', sa.Text(), nullable=False, server_default='planner'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('date', 'variant', name='uq_day_plans_date_variant')
    )
    op.create_index(op.f('ix_day_plans_date'), 'day_plans', ['date'], unique=False)
    op.create_table('time_blocks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('day_plan_id', sa.Integer(), nullable=False),
    sa.Column('start_dt', sa.Text(), nullable=False),
    sa.Column('end_dt', sa.Text(), nullable=False),
    sa.Column('type', sa.Text(), nullable=False),
    sa.Column('task_id', sa.Integer(), nullable=True),
    sa.Column('label', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['day_plan_id'], ['day_plans.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_time_blocks_day_plan_id'), 'time_blocks', ['day_plan_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_time_blocks_day_plan_id'), table_name='time_blocks')
    op.drop_table('time_blocks')
    op.drop_index(op.f('ix_day_plans_date'), table_name='day_plans')
    op.drop_table('day_plans')
