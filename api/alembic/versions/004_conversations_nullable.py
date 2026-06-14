"""Make conversations.customer_id nullable.

Revision ID: 004_conversations_nullable
Revises: 003_add_usage_tracking
Create Date: 2026-06-13 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "004_conversations_nullable"
down_revision: Union[str, None] = "003_add_usage_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Allow conversations that aren't scoped to a single customer."""
    op.execute("ALTER TABLE conversations ALTER COLUMN customer_id DROP NOT NULL")


def downgrade() -> None:
    """Restore the NOT NULL constraint on conversations.customer_id."""
    op.execute("ALTER TABLE conversations ALTER COLUMN customer_id SET NOT NULL")
