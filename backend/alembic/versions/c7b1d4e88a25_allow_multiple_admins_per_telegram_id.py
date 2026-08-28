"""allow multiple admins per telegram id

One person can own more than one reseller panel, so the same Telegram account
must be linkable to several admin rows. Drops the UNIQUE index added by
a4e29d17f6c3 and replaces it with a plain (non-unique) lookup index.

Revision ID: c7b1d4e88a25
Revises: a4e29d17f6c3
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7b1d4e88a25'
down_revision: Union[str, None] = 'a4e29d17f6c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index(op.f('ix_admins_telegram_id'), table_name='admins')
    op.create_index(op.f('ix_admins_telegram_id'), 'admins', ['telegram_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema.

    Note: this can fail if any Telegram ID is linked to more than one admin by
    the time it runs — that data has to be resolved by hand first, since the
    old schema simply cannot represent it.
    """
    op.drop_index(op.f('ix_admins_telegram_id'), table_name='admins')
    op.create_index(op.f('ix_admins_telegram_id'), 'admins', ['telegram_id'], unique=True)
