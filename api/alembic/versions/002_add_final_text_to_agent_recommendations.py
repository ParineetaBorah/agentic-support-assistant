"""Add final_text column to agent_recommendations.

Revision ID: 002_add_final_text
Revises: 001_initial_schema
Create Date: 2026-06-13 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "002_add_final_text"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add a nullable final_text column to agent_recommendations."""
    op.execute("ALTER TABLE agent_recommendations ADD COLUMN final_text TEXT NULL")


def downgrade() -> None:
    """Remove the final_text column from agent_recommendations."""
    op.execute("ALTER TABLE agent_recommendations DROP COLUMN final_text")
