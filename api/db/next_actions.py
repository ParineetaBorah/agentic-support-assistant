"""Queries for the next_actions table."""

from __future__ import annotations

import asyncpg

NEXT_ACTION_COLUMNS = "id, issue_id, recommendation_text, risk_level, created_by, status, created_at"


async def list_next_actions(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    """Return all next actions, most recent first."""
    return await conn.fetch(
        f"""
        SELECT {NEXT_ACTION_COLUMNS}
        FROM next_actions
        ORDER BY created_at DESC
        """
    )


async def get_next_action(conn: asyncpg.Connection, next_action_id: str) -> asyncpg.Record | None:
    """Return a next action by id, or None if it doesn't exist."""
    return await conn.fetchrow(
        f"""
        SELECT {NEXT_ACTION_COLUMNS}
        FROM next_actions
        WHERE id = $1
        """,
        next_action_id,
    )


async def update_next_action_status(
    conn: asyncpg.Connection, next_action_id: str, status: str
) -> asyncpg.Record | None:
    """Update a next action's status and return the updated row, or None if it doesn't exist."""
    return await conn.fetchrow(
        f"""
        UPDATE next_actions
        SET status = $2
        WHERE id = $1
        RETURNING {NEXT_ACTION_COLUMNS}
        """,
        next_action_id,
        status,
    )
