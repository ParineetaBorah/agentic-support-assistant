"""Drop unused conversations.customer_id and conversations.ended_at.

Revision ID: 007_drop_conversation_columns
Revises: 006_issue_update_provenance
Create Date: 2026-06-17 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "007_drop_conversation_columns"
down_revision: Union[str, None] = "006_issue_update_provenance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove the conversation columns no code reads or writes."""
    op.execute("ALTER TABLE conversations DROP COLUMN customer_id")
    op.execute("ALTER TABLE conversations DROP COLUMN ended_at")


def downgrade() -> None:
    """Restore the columns as they stood after 004 (customer_id nullable)."""
    op.execute(
        "ALTER TABLE conversations ADD COLUMN customer_id UUID REFERENCES customers (id)"
    )
    op.execute("ALTER TABLE conversations ADD COLUMN ended_at TIMESTAMPTZ")
