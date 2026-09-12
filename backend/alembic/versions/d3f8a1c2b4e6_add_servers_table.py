"""add servers table

Revision ID: d3f8a1c2b4e6
Revises: f1a2b3c4d5e6
Create Date: 2026-09-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3f8a1c2b4e6'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'servers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('last_seen_at', sa.DateTime(), nullable=True),
        sa.Column('cpu_percent', sa.Float(), nullable=True),
        sa.Column('cpu_cores', sa.Integer(), nullable=True),
        sa.Column('ram_used', sa.BigInteger(), nullable=True),
        sa.Column('ram_total', sa.BigInteger(), nullable=True),
        sa.Column('swap_used', sa.BigInteger(), nullable=True),
        sa.Column('swap_total', sa.BigInteger(), nullable=True),
        sa.Column('disk_used', sa.BigInteger(), nullable=True),
        sa.Column('disk_total', sa.BigInteger(), nullable=True),
        sa.Column('reboot_requested', sa.Boolean(), nullable=True, server_default=sa.false()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_servers_id'), 'servers', ['id'], unique=False)
    op.create_index(op.f('ix_servers_name'), 'servers', ['name'], unique=True)
    op.create_index(op.f('ix_servers_token'), 'servers', ['token'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_servers_token'), table_name='servers')
    op.drop_index(op.f('ix_servers_name'), table_name='servers')
    op.drop_index(op.f('ix_servers_id'), table_name='servers')
    op.drop_table('servers')
