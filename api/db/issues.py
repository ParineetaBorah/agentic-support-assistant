"""Queries for the issues and issue_updates tables."""

from __future__ import annotations

import asyncpg

SEVERITY_ORDER_SQL = (
    "CASE severity "
    "WHEN 'critical' THEN 0 "
    "WHEN 'high' THEN 1 "
    "WHEN 'medium' THEN 2 "
    "WHEN 'low' THEN 3 "
    "END"
)


async def list_open_issues_for_customer(conn: asyncpg.Connection, customer_id: str) -> list[asyncpg.Record]:
    """Return a customer's open (non-closed) issues, most severe first."""
    return await conn.fetch(
        f"""
        SELECT id, title, severity, status, created_at
        FROM issues
        WHERE customer_id = $1 AND status != 'closed'
        ORDER BY {SEVERITY_ORDER_SQL}, created_at
        """,
        customer_id,
    )


async def list_issues(
    conn: asyncpg.Connection,
    customer_id: str | None = None,
    status: str | None = None,
    severity: str | None = None,
) -> list[asyncpg.Record]:
    """Return issues matching the given optional filters, most recent first."""
    conditions = []
    params: list[str] = []
    for column, value in (("customer_id", customer_id), ("status", status), ("severity", severity)):
        if value is not None:
            params.append(value)
            conditions.append(f"{column} = ${len(params)}")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return await conn.fetch(
        f"""
        SELECT id, customer_id, title, description, severity, status, created_at, updated_at
        FROM issues
        {where_clause}
        ORDER BY created_at DESC
        """,
        *params,
    )


async def get_issue(conn: asyncpg.Connection, issue_id: str) -> asyncpg.Record | None:
    """Return an issue by id, or None if it doesn't exist."""
    return await conn.fetchrow(
        """
        SELECT id, customer_id, title, description, severity, status, created_at, updated_at
        FROM issues
        WHERE id = $1
        """,
        issue_id,
    )


async def list_issue_updates(conn: asyncpg.Connection, issue_id: str) -> list[asyncpg.Record]:
    """Return an issue's updates, oldest first."""
    return await conn.fetch(
        """
        SELECT id, update_text, updated_by, created_at
        FROM issue_updates
        WHERE issue_id = $1
        ORDER BY created_at
        """,
        issue_id,
    )


async def insert_issue_update(
    conn: asyncpg.Connection, issue_id: str, update_text: str, updated_by: str
) -> asyncpg.Record:
    """Insert an issue_updates row and return the new row."""
    return await conn.fetchrow(
        """
        INSERT INTO issue_updates (issue_id, update_text, updated_by)
        VALUES ($1, $2, $3)
        RETURNING id, update_text, updated_by, created_at
        """,
        issue_id,
        update_text,
        updated_by,
    )
