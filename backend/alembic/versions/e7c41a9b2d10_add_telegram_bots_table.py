"""add telegram_bots table

Revision ID: e7c41a9b2d10
Revises: e5a6f7b8c9d0
Create Date: 2026-10-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7c41a9b2d10'
down_revision: Union[str, None] = 'e5a6f7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('telegram_bots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('url', sa.String(), nullable=False),
    sa.Column('owner_key', sa.String(), nullable=False),
    sa.Column('manager_key', sa.String(), nullable=False),
    sa.Column('admin_id', sa.Integer(), nullable=True),
    sa.Column('bot_username', sa.String(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['admin_id'], ['admins.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_telegram_bots_id'), 'telegram_bots', ['id'], unique=False)
    op.create_index(op.f('ix_telegram_bots_name'), 'telegram_bots', ['name'], unique=True)
    op.create_index(op.f('ix_telegram_bots_admin_id'), 'telegram_bots', ['admin_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_telegram_bots_admin_id'), table_name='telegram_bots')
    op.drop_index(op.f('ix_telegram_bots_name'), table_name='telegram_bots')
    op.drop_index(op.f('ix_telegram_bots_id'), table_name='telegram_bots')
    op.drop_table('telegram_bots')
