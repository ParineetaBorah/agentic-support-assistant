"""MCP server exposing Acme customer/issue tools backed by Postgres.

Serves over streamable HTTP (default 0.0.0.0:8001). Run from the
mcp_server/ directory:
    python server.py
"""

from __future__ import annotations

import atexit
import json
import os
from pathlib import Path

import httpx
import psycopg2
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from psycopg2 import pool
from psycopg2.extensions import connection as PGConnection
from pydantic import ValidationError

from errors import not_found, permission_denied, validation_error
from models import (
    AddIssueUpdateInput,
    CreateEscalationSummaryInput,
    CreateNextActionInput,
    CustomerProfile,
    EscalationSummary,
    GetCustomerProfileInput,
    GetIssueDetailInput,
    GetOpenIssuesInput,
    IssueDetail,
    IssueUpdate,
    IssueUpdateCreated,
    NextActionCreated,
    OpenIssue,
    OpenIssuesResult,
    RecommendationRecorded,
    RecordRecommendationInput,
)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

POSTGRES_URL = os.environ.get("POSTGRES_URL", "postgresql://postgres:postgres@localhost:5432/acme")
LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
LITELLM_MODEL = os.environ.get("LITELLM_MODEL", "gpt-4o-mini")
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY", "")

MCP_SERVER_HOST = os.environ.get("MCP_SERVER_HOST", "0.0.0.0")
MCP_SERVER_PORT = int(os.environ.get("MCP_SERVER_PORT", "8001"))

ALL_ROLES = {"admin", "support_user", "sales_user"}
ADMIN_ONLY = {"admin"}
SUPPORT_AND_ADMIN = {"support_user", "admin"}

SEVERITY_ORDER_SQL = (
    "CASE severity "
    "WHEN 'critical' THEN 0 "
    "WHEN 'high' THEN 1 "
    "WHEN 'medium' THEN 2 "
    "WHEN 'low' THEN 3 "
    "END"
)

ESCALATION_SYSTEM_PROMPT = (
    "You are a support escalation assistant. Given a customer's name, their open "
    "issues, and recent activity on those issues, respond with a single JSON "
    'object matching this schema: {"risk_level": "low|medium|high|critical", '
    '"summary": str (an executive summary of the customer situation), '
    '"recommendation": str (the recommended next action), '
    '"missing_info": str (any information needed to assess this '
    'situation that is not available here, or an empty string if none)}. '
    "Respond with JSON only, no extra text."
)

mcp = FastMCP("acme-support-tools", host=MCP_SERVER_HOST, port=MCP_SERVER_PORT)


def _check_role(user_role: str, allowed_roles: set[str], tool_name: str) -> None:
    """Raise PermissionError with a structured payload if user_role is not allowed."""
    if user_role not in allowed_roles:
        raise PermissionError(permission_denied(user_role, tool_name))


_pool = pool.ThreadedConnectionPool(minconn=1, maxconn=5, dsn=POSTGRES_URL)


def _get_conn() -> PGConnection:
    """Acquire a connection from the pool."""
    return _pool.getconn()


def _release_conn(conn: PGConnection) -> None:
    """Return a connection to the pool."""
    _pool.putconn(conn)


_CUSTOMER_SELECT = (
    "SELECT c.id, c.name, c.tier, c.industry, u.username "
    "FROM customers c JOIN users u ON u.id = c.account_manager"
)


def _query_customer_exact(conn: PGConnection, customer_name: str) -> tuple | None:
    """Return (id, name, tier, industry, account_manager_name) for an exact case-insensitive match, or None."""
    with conn.cursor() as cur:
        cur.execute(f"{_CUSTOMER_SELECT} WHERE LOWER(c.name) = LOWER(%s)", (customer_name,))
        return cur.fetchone()


def _query_customers_by_prefix(conn: PGConnection, customer_name: str) -> list[tuple]:
    """Return all rows whose name starts with customer_name (case-insensitive)."""
    with conn.cursor() as cur:
        cur.execute(f"{_CUSTOMER_SELECT} WHERE c.name ILIKE %s", (f"{customer_name}%",))
        return cur.fetchall()


def _query_customer_by_id(conn: PGConnection, customer_id: str) -> tuple | None:
    """Return (id, name, tier, industry, account_manager_name) for a customer, or None."""
    with conn.cursor() as cur:
        cur.execute(f"{_CUSTOMER_SELECT} WHERE c.id = %s", (customer_id,))
        return cur.fetchone()


def _query_open_issues(conn: PGConnection, customer_id: str) -> list[tuple]:
    """Return (id, title, severity, status, created_at) for a customer's open issues."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, title, severity, status, created_at
            FROM issues
            WHERE customer_id = %s AND status != 'closed'
            ORDER BY {SEVERITY_ORDER_SQL}, created_at
            """,
            (customer_id,),
        )
        return cur.fetchall()


def _query_open_issues_with_descriptions(conn: PGConnection, customer_id: str) -> list[tuple]:
    """Return (id, title, description, severity, status, created_at) for a customer's open issues."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, title, description, severity, status, created_at
            FROM issues
            WHERE customer_id = %s AND status != 'closed'
            ORDER BY {SEVERITY_ORDER_SQL}, created_at
            """,
            (customer_id,),
        )
        return cur.fetchall()


def _query_issue(conn: PGConnection, issue_id: str) -> tuple | None:
    """Return the full row for an issue, or None if it doesn't exist."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, customer_id, title, description, severity, status, created_at, updated_at
            FROM issues
            WHERE id = %s
            """,
            (issue_id,),
        )
        return cur.fetchone()


def _query_issue_updates(conn: PGConnection, issue_id: str) -> list[tuple]:
    """Return (id, update_text, updated_by, created_at) for an issue's updates, oldest first."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, update_text, updated_by, created_at
            FROM issue_updates
            WHERE issue_id = %s
            ORDER BY created_at
            """,
            (issue_id,),
        )
        return cur.fetchall()


def _upsert_next_action(
    conn: PGConnection,
    issue_id: str,
    recommendation_text: str,
    risk_level: str,
    created_by: str,
    conversation_id: str,
) -> tuple:
    """Insert or update a next_actions row for (issue_id, conversation_id), returning (id, created_at)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO next_actions
                (issue_id, recommendation_text, risk_level, created_by, status, conversation_id)
            VALUES (%s, %s, %s, %s, 'pending', %s)
            ON CONFLICT (issue_id, conversation_id) WHERE conversation_id IS NOT NULL
            DO UPDATE SET
                recommendation_text = EXCLUDED.recommendation_text,
                risk_level = EXCLUDED.risk_level
            RETURNING id, created_at
            """,
            (issue_id, recommendation_text, risk_level, created_by, conversation_id),
        )
        row = cur.fetchone()
    conn.commit()
    return row


def _insert_issue_update(
    conn: PGConnection,
    issue_id: str,
    update_text: str,
    updated_by: str,
    conversation_id: str,
) -> tuple:
    """Insert an agent-authored issue_updates row and return (id, created_at)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO issue_updates (issue_id, update_text, updated_by, source, conversation_id)
            VALUES (%s, %s, %s, 'agent', %s)
            RETURNING id, created_at
            """,
            (issue_id, update_text, updated_by, conversation_id),
        )
        row = cur.fetchone()
    conn.commit()
    return row


def _normalize_text(text: str) -> str:
    """Collapse whitespace and lowercase text for comparison."""
    return " ".join(text.split()).lower()


def _extract_recommendation(tool_output: object) -> str | None:
    """Pull the 'recommendation' field out of a stored escalation-summary tool output."""
    blocks = json.loads(tool_output) if isinstance(tool_output, str) else tool_output
    if not isinstance(blocks, list) or not blocks or not isinstance(blocks[0], dict):
        return None
    text = blocks[0].get("text")
    if not isinstance(text, str):
        return None
    try:
        summary = json.loads(text)
    except json.JSONDecodeError:
        return None
    recommendation = summary.get("recommendation") if isinstance(summary, dict) else None
    return recommendation if isinstance(recommendation, str) else None


def _query_latest_escalation_recommendation(conn: PGConnection, conversation_id: str) -> str | None:
    """Return the recommendation text of the most recent escalation summary in a conversation, or None."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tool_output FROM agent_actions
            WHERE conversation_id = %s AND tool_name = 'create_escalation_summary'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (conversation_id,),
        )
        row = cur.fetchone()
    if row is None or row[0] is None:
        return None
    return _extract_recommendation(row[0])


def _query_next_action_id(conn: PGConnection, conversation_id: str, issue_id: str) -> str | None:
    """Return the next_actions id for an issue within a conversation, or None."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM next_actions
            WHERE conversation_id = %s AND issue_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (conversation_id, issue_id),
        )
        row = cur.fetchone()
    return str(row[0]) if row else None


def _insert_recommendation(
    conn: PGConnection,
    conversation_id: str,
    issue_id: str,
    recommended_text: str,
    risk_level: str,
    outcome: str,
    final_text: str | None,
    next_action_id: str | None,
) -> tuple:
    """Insert an agent_recommendations row and return (id, created_at)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agent_recommendations
                (conversation_id, issue_id, recommended_text, risk_level, outcome, final_text, next_action_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (conversation_id, issue_id, recommended_text, risk_level, outcome, final_text, next_action_id),
        )
        row = cur.fetchone()
    conn.commit()
    return row


def _build_escalation_prompt(customer_name: str, issues_with_updates: list[tuple[tuple, list[tuple]]]) -> str:
    """Render a customer's name, open issues, and update history as plain text for the LLM."""
    lines = [f"Customer: {customer_name}"]
    if not issues_with_updates:
        lines.append("This customer currently has no open issues.")
        return "\n".join(lines)

    for issue_row, update_rows in issues_with_updates:
        _, title, description, severity, status, _ = issue_row
        lines.append(f"Issue: {title} (severity={severity}, status={status})")
        lines.append(f"Description: {description}")
        for update_row in update_rows:
            _, update_text, _, created_at = update_row
            lines.append(f"  - Update ({created_at}): {update_text}")
    return "\n".join(lines)


def _call_llm(issue_summary: str) -> str:
    """Call the LiteLLM proxy and return the raw text content of its response."""
    headers = {}
    if LITELLM_API_KEY:
        headers["Authorization"] = f"Bearer {LITELLM_API_KEY}"

    response = httpx.post(
        f"{LITELLM_URL}/chat/completions",
        json={
            "model": LITELLM_MODEL,
            "messages": [
                {"role": "system", "content": ESCALATION_SYSTEM_PROMPT},
                {"role": "user", "content": issue_summary},
            ],
            "response_format": {"type": "json_object"},
        },
        headers=headers,
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


@mcp.tool()
def get_customer_profile(customer_name: str, user_role: str) -> CustomerProfile:
    """Look up a customer by exact name, then prefix if no exact match."""
    _check_role(user_role, ALL_ROLES, "get_customer_profile")
    GetCustomerProfileInput(customer_name=customer_name, user_role=user_role)

    conn = _get_conn()
    try:
        row = _query_customer_exact(conn, customer_name)
        if row is None:
            rows = _query_customers_by_prefix(conn, customer_name)
            if len(rows) == 1:
                row = rows[0]
            elif len(rows) == 0:
                raise ValueError(not_found("customer", customer_name))
            else:
                names = ", ".join(r[1] for r in rows)
                raise ValueError(
                    validation_error(
                        f"Multiple customers matched '{customer_name}': {names}. Please use the full name."
                    )
                )
    finally:
        _release_conn(conn)

    return CustomerProfile(
        id=str(row[0]),
        name=row[1],
        tier=row[2],
        industry=row[3],
        account_manager=str(row[4]),
    )


@mcp.tool()
def get_open_issues(customer_id: str, user_role: str) -> OpenIssuesResult:
    """List a customer's open issues (status != closed), most severe first."""
    _check_role(user_role, ALL_ROLES, "get_open_issues")
    GetOpenIssuesInput(customer_id=customer_id, user_role=user_role)

    conn = _get_conn()
    try:
        rows = _query_open_issues(conn, customer_id)
    finally:
        _release_conn(conn)

    return OpenIssuesResult(
        issues=[
            OpenIssue(id=str(r[0]), title=r[1], severity=r[2], status=r[3], created_at=r[4])
            for r in rows
        ]
    )


@mcp.tool()
def get_issue_detail(issue_id: str, user_role: str) -> IssueDetail:
    """Return full issue details plus its update history, oldest first."""
    _check_role(user_role, ALL_ROLES, "get_issue_detail")
    GetIssueDetailInput(issue_id=issue_id, user_role=user_role)

    conn = _get_conn()
    try:
        issue_row = _query_issue(conn, issue_id)
        if issue_row is None:
            raise ValueError(not_found("issue", issue_id))
        update_rows = _query_issue_updates(conn, issue_id)
    finally:
        _release_conn(conn)

    return IssueDetail(
        id=str(issue_row[0]),
        customer_id=str(issue_row[1]),
        title=issue_row[2],
        description=issue_row[3],
        severity=issue_row[4],
        status=issue_row[5],
        created_at=issue_row[6],
        updated_at=issue_row[7],
        updates=[
            IssueUpdate(id=str(u[0]), update_text=u[1], updated_by=str(u[2]), created_at=u[3])
            for u in update_rows
        ],
    )


@mcp.tool()
def create_next_action(
    issue_id: str,
    recommendation_text: str,
    risk_level: str,
    user_id: str,
    user_role: str,
    conversation_id: str,
) -> NextActionCreated:
    """Record a recommended next action for an issue. Admins only. At most one action per issue per conversation."""
    _check_role(user_role, ADMIN_ONLY, "create_next_action")
    risk_level = risk_level.strip().lower()
    CreateNextActionInput(
        issue_id=issue_id,
        recommendation_text=recommendation_text,
        risk_level=risk_level,
        user_id=user_id,
        user_role=user_role,
        conversation_id=conversation_id,
    )

    conn = _get_conn()
    try:
        row = _upsert_next_action(conn, issue_id, recommendation_text, risk_level, user_id, conversation_id)
    finally:
        _release_conn(conn)

    return NextActionCreated(id=str(row[0]), created_at=row[1])


@mcp.tool()
def add_issue_update(
    issue_id: str,
    update_text: str,
    user_id: str,
    user_role: str,
    conversation_id: str,
) -> IssueUpdateCreated:
    """Append a progress note to an issue's activity log. Support and admin only."""
    _check_role(user_role, SUPPORT_AND_ADMIN, "add_issue_update")
    AddIssueUpdateInput(
        issue_id=issue_id,
        update_text=update_text,
        user_id=user_id,
        user_role=user_role,
        conversation_id=conversation_id,
    )

    conn = _get_conn()
    try:
        if _query_issue(conn, issue_id) is None:
            raise ValueError(not_found("issue", issue_id))
        row = _insert_issue_update(conn, issue_id, update_text, user_id, conversation_id)
    finally:
        _release_conn(conn)

    return IssueUpdateCreated(id=str(row[0]), created_at=row[1])


@mcp.tool()
def record_recommendation(
    issue_id: str,
    recommended_text: str,
    risk_level: str,
    outcome: str,
    user_role: str,
    conversation_id: str,
) -> RecommendationRecorded:
    """Record the outcome of a proposed next action. Support and admin only.

    Pass outcome='dismissed' when the user rejects, or outcome='accepted' when
    the user accepts (committing a next action). For an accepted outcome the
    server compares the committed text against the original escalation-summary
    recommendation and reclassifies it as 'edited' if it differs; the link to
    the next action is resolved automatically.
    """
    _check_role(user_role, SUPPORT_AND_ADMIN, "record_recommendation")
    risk_level = risk_level.strip().lower()
    RecordRecommendationInput(
        issue_id=issue_id,
        recommended_text=recommended_text,
        risk_level=risk_level,
        outcome=outcome,
        user_role=user_role,
        conversation_id=conversation_id,
    )

    conn = _get_conn()
    try:
        if _query_issue(conn, issue_id) is None:
            raise ValueError(not_found("issue", issue_id))

        if outcome == "dismissed":
            final_outcome, stored_recommended, stored_final, next_action_id = (
                "dismissed",
                recommended_text,
                None,
                None,
            )
        else:
            original = _query_latest_escalation_recommendation(conn, conversation_id)
            next_action_id = _query_next_action_id(conn, conversation_id, issue_id)
            if original is not None and _normalize_text(original) != _normalize_text(recommended_text):
                final_outcome, stored_recommended, stored_final = "edited", original, recommended_text
            else:
                final_outcome, stored_recommended, stored_final = "accepted", recommended_text, None

        row = _insert_recommendation(
            conn,
            conversation_id=conversation_id,
            issue_id=issue_id,
            recommended_text=stored_recommended,
            risk_level=risk_level,
            outcome=final_outcome,
            final_text=stored_final,
            next_action_id=next_action_id,
        )
    finally:
        _release_conn(conn)

    return RecommendationRecorded(id=str(row[0]), outcome=final_outcome, created_at=row[1])


@mcp.tool()
def create_escalation_summary(customer_id: str, user_role: str) -> EscalationSummary:
    """Summarize a customer's open issues into a risk-rated escalation via LLM."""
    _check_role(user_role, SUPPORT_AND_ADMIN, "create_escalation_summary")
    CreateEscalationSummaryInput(customer_id=customer_id, user_role=user_role)

    conn = _get_conn()
    try:
        customer_row = _query_customer_by_id(conn, customer_id)
        if customer_row is None:
            raise ValueError(not_found("customer", customer_id))
        issue_rows = _query_open_issues_with_descriptions(conn, customer_id)
        issues_with_updates = [
            (issue_row, _query_issue_updates(conn, issue_row[0])) for issue_row in issue_rows
        ]
    finally:
        _release_conn(conn)

    raw_output = _call_llm(_build_escalation_prompt(customer_row[1], issues_with_updates))

    try:
        return EscalationSummary.model_validate_json(raw_output)
    except ValidationError as exc:
        raise ValueError(validation_error(f"LLM output failed validation: {exc}")) from exc


atexit.register(_pool.closeall)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
