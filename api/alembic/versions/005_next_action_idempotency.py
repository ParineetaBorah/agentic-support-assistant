"""Add conversation_id to next_actions for per-conversation idempotency.

Revision ID: 005_next_action_idempotency
Revises: 004_conversations_nullable
Create Date: 2026-06-14 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005_next_action_idempotency"
down_revision: Union[str, None] = "004_conversations_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add conversation_id column and unique(issue_id, conversation_id) constraint."""
    op.execute("""
        ALTER TABLE next_actions
        ADD COLUMN conversation_id UUID REFERENCES conversations (id)
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_next_actions_issue_conversation
        ON next_actions (issue_id, conversation_id)
        WHERE conversation_id IS NOT NULL
    """)


def downgrade() -> None:
    """Remove the unique index and conversation_id column."""
    op.execute("DROP INDEX uq_next_actions_issue_conversation")
    op.execute("ALTER TABLE next_actions DROP COLUMN conversation_id")
