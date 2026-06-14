"""Queries for the customers table."""

from __future__ import annotations

import asyncpg


async def list_customers(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    """Return all customers, ordered by name."""
    return await conn.fetch(
        """
        SELECT id, name, tier, industry, account_manager, created_at
        FROM customers
        ORDER BY name
        """
    )


async def get_customer(conn: asyncpg.Connection, customer_id: str) -> asyncpg.Record | None:
    """Return a customer by id, or None if it doesn't exist."""
    return await conn.fetchrow(
        """
        SELECT id, name, tier, industry, account_manager, created_at
        FROM customers
        WHERE id = $1
        """,
        customer_id,
    )
