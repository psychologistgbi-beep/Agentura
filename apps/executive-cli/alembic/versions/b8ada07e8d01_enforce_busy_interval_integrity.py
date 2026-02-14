"""enforce busy interval integrity

Revision ID: b8ada07e8d01
Revises: b7e2c3d41a09
Create Date: 2026-02-14 16:15:22.893639

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b8ada07e8d01'
down_revision: Union[str, Sequence[str], None] = 'b7e2c3d41a09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("busy_blocks", recreate="always") as batch_op:
        batch_op.create_check_constraint(
            "ck_busy_blocks_end_after_start",
            "julianday(end_dt) > julianday(start_dt)",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("busy_blocks", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_busy_blocks_end_after_start", type_="check")
