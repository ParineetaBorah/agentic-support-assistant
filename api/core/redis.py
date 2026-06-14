"""Redis-backed conversation history cache.

Keys follow the pattern conv:{conversation_id} and hold a JSON-encoded list
of {"role": ..., "content": ...} turns, refreshed to a 1 hour TTL on write.
"""

from __future__ import annotations

import json

from redis import asyncio as redis_asyncio

from core.config import settings

CONVERSATION_TTL_SECONDS = 60 * 60

_redis: redis_asyncio.Redis | None = None


def get_redis() -> redis_asyncio.Redis:
    """Return the shared async Redis client, creating it on first call."""
    global _redis
    if _redis is None:
        _redis = redis_asyncio.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    """Close the shared Redis client, if it was created."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def _conversation_key(conversation_id: str) -> str:
    """Return the Redis key holding a conversation's cached turn history."""
    return f"conv:{conversation_id}"


async def get_conversation_history(conversation_id: str) -> list[dict]:
    """Return the cached turns for a conversation, oldest first, or [] on a cache miss."""
    client = get_redis()
    raw_turns = await client.lrange(_conversation_key(conversation_id), 0, -1)
    return [json.loads(turn) for turn in raw_turns]


async def save_conversation_turn(conversation_id: str, role: str, content: str) -> None:
    """Append a turn to the conversation's cache and refresh its TTL."""
    client = get_redis()
    key = _conversation_key(conversation_id)
    await client.rpush(key, json.dumps({"role": role, "content": content}))
    await client.expire(key, CONVERSATION_TTL_SECONDS)


async def clear_conversation(conversation_id: str) -> None:
    """Remove a conversation's cached turn history."""
    client = get_redis()
    await client.delete(_conversation_key(conversation_id))
