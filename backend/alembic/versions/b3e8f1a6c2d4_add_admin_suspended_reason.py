"""add suspended_reason for admins

Revision ID: b3e8f1a6c2d4
Revises: f2a7c9d1e3b5
Create Date: 2026-10-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3e8f1a6c2d4'
down_revision: Union[str, None] = 'f2a7c9d1e3b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('admins', sa.Column('suspended_reason', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('admins') as batch_op:
        batch_op.drop_column('suspended_reason')
