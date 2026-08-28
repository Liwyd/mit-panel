"""add telegram id for admins

Revision ID: a4e29d17f6c3
Revises: 8c82eb6a7c50
Create Date: 2026-08-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4e29d17f6c3'
down_revision: Union[str, None] = '8c82eb6a7c50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('admins', sa.Column('telegram_id', sa.BigInteger(), nullable=True))
    op.create_index(op.f('ix_admins_telegram_id'), 'admins', ['telegram_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_admins_telegram_id'), table_name='admins')
    op.drop_column('admins', 'telegram_id')
