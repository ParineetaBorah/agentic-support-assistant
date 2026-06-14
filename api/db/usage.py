"""Queries for usage and cost tracking across conversation_turns."""

from __future__ import annotations

import asyncpg


async def get_conversation_usage_turns(conn: asyncpg.Connection, conversation_id: str) -> list[asyncpg.Record]:
    """Return a conversation's turns with usage/cost columns, oldest first."""
    return await conn.fetch(
        """
        SELECT id, role, prompt_tokens, completion_tokens, total_tokens, cost_usd, model_used, created_at
        FROM conversation_turns
        WHERE conversation_id = $1
        ORDER BY created_at
        """,
        conversation_id,
    )


async def get_user_usage(conn: asyncpg.Connection, user_id: str) -> asyncpg.Record:
    """Return the conversation count, total cost, and total tokens for a user."""
    return await conn.fetchrow(
        """
        SELECT
            COUNT(DISTINCT c.id) AS conversation_count,
            COALESCE(SUM(t.cost_usd), 0) AS total_cost_usd,
            COALESCE(SUM(t.total_tokens), 0) AS total_tokens
        FROM conversations c
        LEFT JOIN conversation_turns t ON t.conversation_id = c.id
        WHERE c.user_id = $1
        """,
        user_id,
    )


async def get_usage_summary(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    """Return call count, total cost, and total tokens grouped by model_used."""
    return await conn.fetch(
        """
        SELECT
            model_used,
            COUNT(*) AS call_count,
            COALESCE(SUM(cost_usd), 0) AS total_cost_usd,
            COALESCE(SUM(total_tokens), 0) AS total_tokens
        FROM conversation_turns
        WHERE model_used IS NOT NULL
        GROUP BY model_used
        ORDER BY total_cost_usd DESC
        """
    )
