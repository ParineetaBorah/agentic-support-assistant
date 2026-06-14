"""Add source and conversation_id to issue_updates for agent-write provenance.

Revision ID: 006_issue_update_provenance
Revises: 005_next_action_idempotency
Create Date: 2026-06-14 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006_issue_update_provenance"
down_revision: Union[str, None] = "005_next_action_idempotency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add a source provenance column and a nullable conversation_id link."""
    op.execute(
        "ALTER TABLE issue_updates "
        "ADD COLUMN source TEXT NOT NULL DEFAULT 'human' CHECK (source IN ('human', 'agent'))"
    )
    op.execute("ALTER TABLE issue_updates ADD COLUMN conversation_id UUID REFERENCES conversations (id)")


def downgrade() -> None:
    """Remove the conversation_id link and source provenance column."""
    op.execute("ALTER TABLE issue_updates DROP COLUMN conversation_id")
    op.execute("ALTER TABLE issue_updates DROP COLUMN source")
