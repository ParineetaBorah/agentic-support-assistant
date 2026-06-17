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
        SELECT id, user_id, started_at
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
        INNER JOIN conversation_turns t ON t.conversation_id = c.id
        WHERE c.user_id = $1
        GROUP BY c.id, c.started_at
        ORDER BY last_turn_at DESC
        LIMIT 50
        """,
        user_id,
    )


async def list_conversation_turns(conn: asyncpg.Connection, conversation_id: str) -> list[asyncpg.Record]:
    """Return a conversation's turns, oldest first, each with its tool calls in call order."""
    return await conn.fetch(
        """
        SELECT
            t.id,
            t.role,
            t.content,
            t.created_at,
            COALESCE(
                array_agg(a.tool_name ORDER BY a.created_at)
                    FILTER (WHERE a.tool_name IS NOT NULL),
                '{}'
            ) AS tools_called
        FROM conversation_turns t
        LEFT JOIN agent_actions a ON a.turn_id = t.id
        WHERE t.conversation_id = $1
        GROUP BY t.id, t.role, t.content, t.created_at
        ORDER BY t.created_at
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


_ENTITY_TOOLS = ("get_customer_profile", "get_open_issues", "get_issue_detail")


def _loads(value: object) -> object:
    """Parse a jsonb value (asyncpg returns it as a string), or pass through if already decoded."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _tool_result(tool_output: object) -> dict | None:
    """Extract the result object from an agent_actions.tool_output MCP content-block list."""
    blocks = _loads(tool_output)
    if isinstance(blocks, list) and blocks and isinstance(blocks[0], dict):
        text = blocks[0].get("text")
        parsed = _loads(text) if isinstance(text, str) else None
        return parsed if isinstance(parsed, dict) else None
    return blocks if isinstance(blocks, dict) else None


async def fetch_known_entities(conn: asyncpg.Connection, conversation_id: str) -> str:
    """Reconstruct resolved UUIDs for the most recently looked-up customer as a prompt block.

    Scoped to the current customer (the last get_customer_profile in the
    conversation) to avoid cross-customer confusion, with issues grouped under
    it. Returns "" if no customer has been resolved yet.
    """
    rows = await conn.fetch(
        """
        SELECT tool_name, tool_input, tool_output
        FROM agent_actions
        WHERE conversation_id = $1 AND tool_name = ANY($2::text[])
        ORDER BY created_at
        """,
        conversation_id,
        list(_ENTITY_TOOLS),
    )

    customer_names: dict[str, str] = {}
    issues_by_customer: dict[str, dict[str, str]] = {}
    current_customer_id: str | None = None

    for row in rows:
        result = _tool_result(row["tool_output"])
        args = _loads(row["tool_input"])
        args = args if isinstance(args, dict) else {}
        if row["tool_name"] == "get_customer_profile" and isinstance(result, dict) and result.get("id"):
            customer_names[result["id"]] = result.get("name", result["id"])
            current_customer_id = result["id"]
        elif row["tool_name"] == "get_open_issues" and isinstance(result, dict) and args.get("customer_id"):
            bucket = issues_by_customer.setdefault(args["customer_id"], {})
            for issue in result.get("issues", []):
                if isinstance(issue, dict) and issue.get("id") and issue.get("title"):
                    bucket[issue["title"]] = issue["id"]
        elif row["tool_name"] == "get_issue_detail" and isinstance(result, dict):
            cid, iid, title = result.get("customer_id"), result.get("id"), result.get("title")
            if cid and iid and title:
                issues_by_customer.setdefault(cid, {})[title] = iid

    if current_customer_id is None:
        return ""

    lines = [
        "KNOWN IDENTIFIERS (resolved earlier in this conversation; use these UUIDs directly as tool "
        "arguments — do not re-resolve or guess):",
        f"{customer_names[current_customer_id]} ({current_customer_id}):",
    ]
    for title, issue_id in issues_by_customer.get(current_customer_id, {}).items():
        lines.append(f"  - {title} = {issue_id}")
    return "\n".join(lines)
