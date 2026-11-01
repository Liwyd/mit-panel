"""add marzban_users ledger

Revision ID: f2a7c9d1e3b5
Revises: e7c41a9b2d10
Create Date: 2026-10-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a7c9d1e3b5'
down_revision: Union[str, None] = 'e7c41a9b2d10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('marzban_users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner', sa.String(), nullable=False),
    sa.Column('username', sa.String(), nullable=False),
    sa.Column('data_limit', sa.BigInteger(), nullable=False, server_default='0'),
    sa.Column('used_traffic', sa.BigInteger(), nullable=False, server_default='0'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('owner', 'username')
    )
    op.create_index(op.f('ix_marzban_users_id'), 'marzban_users', ['id'], unique=False)
    op.create_index(op.f('ix_marzban_users_owner'), 'marzban_users', ['owner'], unique=False)
    # Null for every existing admin: the first sync adopts the users already
    # on Marzban without charging, so upgrading never bills old users twice.
    op.add_column('admins', sa.Column('marzban_synced_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('admins') as batch_op:
        batch_op.drop_column('marzban_synced_at')
    op.drop_index(op.f('ix_marzban_users_owner'), table_name='marzban_users')
    op.drop_index(op.f('ix_marzban_users_id'), table_name='marzban_users')
    op.drop_table('marzban_users')
