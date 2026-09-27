"""add marzban_users ledger

Revision ID: e5a6f7b8c9d0
Revises: d3f8a1c2b4e6
Create Date: 2026-09-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a6f7b8c9d0'
down_revision: Union[str, None] = 'd3f8a1c2b4e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'marzban_users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('owner', sa.String(), nullable=False),
        sa.Column('data_limit', sa.BigInteger(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner', 'username', name='uq_marzban_users_owner_username'),
    )
    op.create_index(op.f('ix_marzban_users_id'), 'marzban_users', ['id'], unique=False)
    op.create_index(op.f('ix_marzban_users_username'), 'marzban_users', ['username'], unique=False)
    op.create_index(op.f('ix_marzban_users_owner'), 'marzban_users', ['owner'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_marzban_users_owner'), table_name='marzban_users')
    op.drop_index(op.f('ix_marzban_users_username'), table_name='marzban_users')
    op.drop_index(op.f('ix_marzban_users_id'), table_name='marzban_users')
    op.drop_table('marzban_users')
