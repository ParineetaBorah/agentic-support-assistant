"""Initial schema: users, customers, issues, and related tables.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-06-13 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the initial schema for users, customers, issues, and related tables."""
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.execute("""
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL CHECK (role IN ('admin', 'support_user', 'sales_user')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE customers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            tier TEXT NOT NULL CHECK (tier IN ('enterprise', 'smb', 'startup')),
            industry TEXT NOT NULL,
            account_manager UUID NOT NULL REFERENCES users (id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE issues (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            customer_id UUID NOT NULL REFERENCES customers (id),
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            severity TEXT NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low')),
            status TEXT NOT NULL CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE issue_updates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            issue_id UUID NOT NULL REFERENCES issues (id),
            update_text TEXT NOT NULL,
            updated_by UUID NOT NULL REFERENCES users (id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE next_actions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            issue_id UUID NOT NULL REFERENCES issues (id),
            recommendation_text TEXT NOT NULL,
            risk_level TEXT NOT NULL CHECK (risk_level IN ('critical', 'high', 'medium', 'low')),
            created_by UUID NOT NULL REFERENCES users (id),
            status TEXT NOT NULL CHECK (status IN ('pending', 'completed')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE conversations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users (id),
            customer_id UUID NOT NULL REFERENCES customers (id),
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            ended_at TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE TABLE conversation_turns (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL REFERENCES conversations (id),
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE agent_actions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL REFERENCES conversations (id),
            turn_id UUID REFERENCES conversation_turns (id),
            tool_name TEXT NOT NULL,
            tool_input JSONB,
            tool_output JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE agent_recommendations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL REFERENCES conversations (id),
            issue_id UUID NOT NULL REFERENCES issues (id),
            recommended_text TEXT NOT NULL,
            risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
            outcome TEXT NOT NULL DEFAULT 'pending' CHECK (outcome IN ('accepted', 'edited', 'dismissed', 'pending')),
            next_action_id UUID REFERENCES next_actions (id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("CREATE INDEX idx_issues_customer_id ON issues (customer_id)")
    op.execute("CREATE INDEX idx_issues_status ON issues (status)")
    op.execute("CREATE INDEX idx_issues_severity ON issues (severity)")
    op.execute("CREATE INDEX idx_agent_actions_conversation_id ON agent_actions (conversation_id)")
    op.execute(
        "CREATE INDEX idx_agent_recommendations_conversation_issue_outcome "
        "ON agent_recommendations (conversation_id, issue_id, outcome)"
    )
    op.execute("CREATE INDEX idx_conversation_turns_conversation_id ON conversation_turns (conversation_id)")


def downgrade() -> None:
    """Drop all tables and the pgcrypto extension created by upgrade()."""
    op.execute("DROP TABLE agent_recommendations")
    op.execute("DROP TABLE agent_actions")
    op.execute("DROP TABLE conversation_turns")
    op.execute("DROP TABLE conversations")
    op.execute("DROP TABLE next_actions")
    op.execute("DROP TABLE issue_updates")
    op.execute("DROP TABLE issues")
    op.execute("DROP TABLE customers")
    op.execute("DROP TABLE users")
    op.execute('DROP EXTENSION "pgcrypto"')
