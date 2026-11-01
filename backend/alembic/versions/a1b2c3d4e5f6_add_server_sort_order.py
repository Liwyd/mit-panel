"""add server sort_order

Revision ID: a1b2c3d4e5f6
Revises: d3f8a1c2b4e6
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'd3f8a1c2b4e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('servers', sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))
    # Seed existing rows with their current id-based order so nothing
    # collapses to the same position.
    op.execute(
        "UPDATE servers SET sort_order = id WHERE sort_order = 0"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('servers', 'sort_order')
