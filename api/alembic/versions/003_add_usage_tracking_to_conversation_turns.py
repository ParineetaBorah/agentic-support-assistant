"""Add usage and cost tracking columns to conversation_turns.

Revision ID: 003_add_usage_tracking
Revises: 002_add_final_text
Create Date: 2026-06-13 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "003_add_usage_tracking"
down_revision: Union[str, None] = "002_add_final_text"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add per-turn token usage and cost columns to conversation_turns."""
    op.execute("""
        ALTER TABLE conversation_turns
        ADD COLUMN prompt_tokens INTEGER,
        ADD COLUMN completion_tokens INTEGER,
        ADD COLUMN total_tokens INTEGER,
        ADD COLUMN cost_usd NUMERIC(10, 6),
        ADD COLUMN model_used TEXT
    """)


def downgrade() -> None:
    """Remove the token usage and cost columns from conversation_turns."""
    op.execute("""
        ALTER TABLE conversation_turns
        DROP COLUMN prompt_tokens,
        DROP COLUMN completion_tokens,
        DROP COLUMN total_tokens,
        DROP COLUMN cost_usd,
        DROP COLUMN model_used
    """)
