"""Asyncpg connection pool, initialised once from main.py's lifespan."""

from __future__ import annotations

from typing import AsyncIterator

import asyncpg

from core.config import settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Return the shared connection pool, creating it on first call."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings.postgres_url)
    return _pool


async def close_pool() -> None:
    """Close the shared connection pool, if it was created."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def get_db() -> AsyncIterator[asyncpg.Connection]:
    """FastAPI dependency yielding a connection from the shared pool."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn
