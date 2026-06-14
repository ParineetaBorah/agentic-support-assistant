"""Queries for the conversations, conversation_turns, and agent_actions tables."""

from __future__ import annotations

import json

import asyncpg


async def create_conversation(conn: asyncpg.Connection, user_id: str) -> asyncpg.Record:
    """Insert a new conversation for user_id and return its id and started_at."""
    return await conn.fetchrow(
        """
        INSERT INTO conversations (user_id)
        VALUES ($1)
        RETURNING id, started_at
        """,
        user_id,
    )


async def get_conversation(conn: asyncpg.Connection, conversation_id: str) -> asyncpg.Record | None:
    """Return a conversation by id, or None if it doesn't exist."""
    return await conn.fetchrow(
        """
        SELECT id, user_id, customer_id, started_at, ended_at
        FROM conversations
        WHERE id = $1
        """,
        conversation_id,
    )


async def list_conversations(conn: asyncpg.Connection, user_id: str) -> list[asyncpg.Record]:
    """Return user_id's 50 most recent conversations, newest activity first."""
    return await conn.fetch(
        """
        SELECT
            c.id,
            cust.name AS customer_name,
            c.started_at,
            MAX(t.created_at) AS last_turn_at,
            COUNT(t.id) AS turn_count,
            (
                SELECT LEFT(content, 60)
                FROM conversation_turns
                WHERE conversation_id = c.id AND role = 'user'
                ORDER BY created_at
                LIMIT 1
            ) AS preview
        FROM conversations c
        LEFT JOIN customers cust ON cust.id = c.customer_id
        INNER JOIN conversation_turns t ON t.conversation_id = c.id
        WHERE c.user_id = $1
        GROUP BY c.id, cust.name, c.started_at
        ORDER BY last_turn_at DESC
        LIMIT 50
        """,
        user_id,
    )


async def list_conversation_turns(conn: asyncpg.Connection, conversation_id: str) -> list[asyncpg.Record]:
    """Return a conversation's turns, oldest first."""
    return await conn.fetch(
        """
        SELECT id, role, content, created_at
        FROM conversation_turns
        WHERE conversation_id = $1
        ORDER BY created_at
        """,
        conversation_id,
    )


async def insert_conversation_turn(
    conn: asyncpg.Connection,
    conversation_id: str,
    role: str,
    content: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    cost_usd: float | None = None,
    model_used: str | None = None,
) -> asyncpg.Record:
    """Insert a conversation_turns row and return its id and created_at."""
    return await conn.fetchrow(
        """
        INSERT INTO conversation_turns
            (conversation_id, role, content, prompt_tokens, completion_tokens, total_tokens, cost_usd, model_used)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id, created_at
        """,
        conversation_id,
        role,
        content,
        prompt_tokens,
        completion_tokens,
        total_tokens,
        cost_usd,
        model_used,
    )


def _as_jsonb(value: str | dict) -> str:
    """Encode a value for a jsonb column, avoiding double-encoding already-JSON strings."""
    if isinstance(value, str):
        try:
            json.loads(value)
            return value
        except json.JSONDecodeError:
            return json.dumps(value)
    return json.dumps(value)


async def insert_agent_action(
    conn: asyncpg.Connection,
    conversation_id: str,
    turn_id: str,
    tool_name: str,
    tool_input: dict,
    tool_output: str,
) -> None:
    """Insert an agent_actions row recording one tool call made during a turn."""
    await conn.execute(
        """
        INSERT INTO agent_actions (conversation_id, turn_id, tool_name, tool_input, tool_output)
        VALUES ($1, $2, $3, $4, $5)
        """,
        conversation_id,
        turn_id,
        tool_name,
        _as_jsonb(tool_input),
        _as_jsonb(tool_output),
    )
