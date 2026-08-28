"""add marzban_all_inbounds

Revision ID: f1a2b3c4d5e6
Revises: c7b1d4e88a25
Create Date: 2026-08-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'c7b1d4e88a25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'admins',
        sa.Column('marzban_all_inbounds', sa.Boolean(), nullable=True, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('admins', 'marzban_all_inbounds')
