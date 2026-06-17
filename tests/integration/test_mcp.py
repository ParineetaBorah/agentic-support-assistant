"""Direct (non-agent) checks of the MCP server's tools against a running Postgres.

Requires Postgres reachable via POSTGRES_URL with migrations applied and seed
data loaded (api/db/migrate.sh). create_escalation_summary additionally
requires LITELLM_URL to point at a running LiteLLM proxy. Run with:
    python tests/test_mcp.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "mcp_server"))

from models import (  # noqa: E402
    CustomerProfile,
    EscalationSummary,
    IssueDetail,
    IssueUpdateCreated,
    NextActionCreated,
    OpenIssuesResult,
    RecommendationRecorded,
)
from server import (  # noqa: E402
    _get_conn,
    _release_conn,
    add_issue_update,
    create_escalation_summary,
    create_next_action,
    get_customer_profile,
    get_issue_detail,
    get_open_issues,
    record_recommendation,
)

SEVERITY_ORDER = ["critical", "high", "medium", "low"]

GLOBEX_CUSTOMER_ID = "a1000000-0000-0000-0000-000000000001"
GLOBEX_ISSUE_ID = "c1000000-0000-0000-0000-000000000001"
ADMIN_USER_ID = "b1000000-0000-0000-0000-000000000003"


def _create_test_conversation() -> str:
    """Insert a temporary conversation row and return its UUID string."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO conversations (user_id) VALUES (%s) RETURNING id",
                (ADMIN_USER_ID,),
            )
            row = cur.fetchone()
        conn.commit()
        return str(row[0])
    finally:
        _release_conn(conn)


def check(name: str, fn: Callable[[], None]) -> None:
    """Run fn and print PASS/FAIL for the named check."""
    try:
        fn()
        print(f"PASS: {name}")
    except Exception as exc:
        print(f"FAIL: {name} -> {exc}")


def test_get_customer_profile() -> None:
    """get_customer_profile finds Globex Corp case-insensitively for any role."""
    profile = get_customer_profile(customer_name="globex corp", user_role="sales_user")
    assert isinstance(profile, CustomerProfile)
    assert profile.id == GLOBEX_CUSTOMER_ID
    assert profile.name == "Globex Corp"
    assert profile.tier == "enterprise"


def test_get_customer_profile_not_found() -> None:
    """get_customer_profile raises ValueError for an unknown customer."""
    try:
        get_customer_profile(customer_name="Nonexistent Inc", user_role="admin")
    except ValueError as exc:
        assert "not found" in str(exc)
        return
    raise AssertionError("expected ValueError for unknown customer")


def test_get_customer_profile_prefix_match() -> None:
    """get_customer_profile resolves a prefix like 'Globex' to 'Globex Corp'."""
    profile = get_customer_profile(customer_name="Globex", user_role="sales_user")
    assert isinstance(profile, CustomerProfile)
    assert profile.id == GLOBEX_CUSTOMER_ID
    assert profile.name == "Globex Corp"


def test_get_customer_profile_multi_match() -> None:
    """get_customer_profile returns validation_error when the prefix is ambiguous."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO customers (id, name, tier, industry, account_manager) "
                "VALUES ('a9999999-0000-0000-0000-000000000001', 'Globex Industries', 'smb', 'Tech', %s)"
                " ON CONFLICT DO NOTHING",
                (ADMIN_USER_ID,),
            )
        conn.commit()
    finally:
        _release_conn(conn)

    try:
        get_customer_profile(customer_name="Globex", user_role="admin")
    except ValueError as exc:
        assert "Multiple customers matched" in str(exc)
        assert "Globex Corp" in str(exc)
        assert "Globex Industries" in str(exc)
    else:
        raise AssertionError("expected ValueError for ambiguous prefix")
    finally:
        conn2 = _get_conn()
        try:
            with conn2.cursor() as cur:
                cur.execute(
                    "DELETE FROM customers WHERE id = 'a9999999-0000-0000-0000-000000000001'"
                )
            conn2.commit()
        finally:
            _release_conn(conn2)


def test_get_customer_profile_prefix_not_found() -> None:
    """get_customer_profile returns not_found when prefix matches nothing."""
    try:
        get_customer_profile(customer_name="FooBar", user_role="admin")
    except ValueError as exc:
        assert "not found" in str(exc)
        return
    raise AssertionError("expected ValueError for non-existent prefix")


def test_get_open_issues() -> None:
    """get_open_issues returns Globex's open issues ordered by severity."""
    result = get_open_issues(customer_id=GLOBEX_CUSTOMER_ID, user_role="support_user")
    assert isinstance(result, OpenIssuesResult)
    assert len(result.issues) >= 1
    assert all(issue.status != "closed" for issue in result.issues)
    severities = [issue.severity for issue in result.issues]
    assert severities == sorted(severities, key=SEVERITY_ORDER.index)


def test_get_issue_detail() -> None:
    """get_issue_detail returns the issue plus its update history."""
    detail = get_issue_detail(issue_id=GLOBEX_ISSUE_ID, user_role="sales_user")
    assert isinstance(detail, IssueDetail)
    assert detail.id == GLOBEX_ISSUE_ID
    assert detail.customer_id == GLOBEX_CUSTOMER_ID


def test_create_next_action() -> None:
    """create_next_action upserts for admin; second call on same conv returns same id."""
    conv_id = _create_test_conversation()
    result = create_next_action(
        issue_id=GLOBEX_ISSUE_ID,
        recommendation_text="Escalate to infrastructure on-call.",
        risk_level="high",
        user_id=ADMIN_USER_ID,
        user_role="admin",
        conversation_id=conv_id,
    )
    assert isinstance(result, NextActionCreated)
    result2 = create_next_action(
        issue_id=GLOBEX_ISSUE_ID,
        recommendation_text="Updated recommendation.",
        risk_level="critical",
        user_id=ADMIN_USER_ID,
        user_role="admin",
        conversation_id=conv_id,
    )
    assert result2.id == result.id


def test_create_next_action_permission_sales_user() -> None:
    """create_next_action raises PermissionError for sales_user."""
    try:
        create_next_action(
            issue_id=GLOBEX_ISSUE_ID,
            recommendation_text="Should not be allowed.",
            risk_level="low",
            user_id=ADMIN_USER_ID,
            user_role="sales_user",
            conversation_id="test-conv-id",
        )
    except PermissionError:
        return
    raise AssertionError("expected PermissionError for sales_user")


def test_create_next_action_permission_support_user() -> None:
    """create_next_action raises PermissionError for support_user."""
    try:
        create_next_action(
            issue_id=GLOBEX_ISSUE_ID,
            recommendation_text="Should not be allowed.",
            risk_level="low",
            user_id=ADMIN_USER_ID,
            user_role="support_user",
            conversation_id="test-conv-id",
        )
    except PermissionError:
        return
    raise AssertionError("expected PermissionError for support_user")


def test_add_issue_update() -> None:
    """add_issue_update appends a note for support_user and returns IssueUpdateCreated."""
    conv_id = _create_test_conversation()
    result = add_issue_update(
        issue_id=GLOBEX_ISSUE_ID,
        update_text="Restarted the primary database; monitoring connection counts.",
        user_id=ADMIN_USER_ID,
        user_role="support_user",
        conversation_id=conv_id,
    )
    assert isinstance(result, IssueUpdateCreated)


def test_add_issue_update_permission_sales_user() -> None:
    """add_issue_update raises PermissionError for sales_user."""
    try:
        add_issue_update(
            issue_id=GLOBEX_ISSUE_ID,
            update_text="Should not be allowed.",
            user_id=ADMIN_USER_ID,
            user_role="sales_user",
            conversation_id="test-conv-id",
        )
    except PermissionError:
        return
    raise AssertionError("expected PermissionError for sales_user")


def test_record_recommendation() -> None:
    """record_recommendation persists a dismissed outcome for support_user."""
    conv_id = _create_test_conversation()
    result = record_recommendation(
        issue_id=GLOBEX_ISSUE_ID,
        recommended_text="Escalate to the infrastructure on-call team.",
        risk_level="high",
        outcome="dismissed",
        user_role="support_user",
        conversation_id=conv_id,
    )
    assert isinstance(result, RecommendationRecorded)
    assert result.outcome == "dismissed"


def test_record_recommendation_accepted_links() -> None:
    """An accepted recommendation auto-links to the next action for the same issue and conversation."""
    conv_id = _create_test_conversation()
    create_next_action(
        issue_id=GLOBEX_ISSUE_ID,
        recommendation_text="Escalate to infrastructure on-call.",
        risk_level="high",
        user_id=ADMIN_USER_ID,
        user_role="admin",
        conversation_id=conv_id,
    )
    result = record_recommendation(
        issue_id=GLOBEX_ISSUE_ID,
        recommended_text="Escalate to infrastructure on-call.",
        risk_level="high",
        outcome="accepted",
        user_role="admin",
        conversation_id=conv_id,
    )
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT next_action_id FROM agent_recommendations WHERE id = %s", (result.id,))
            row = cur.fetchone()
    finally:
        _release_conn(conn)
    assert row[0] is not None


def test_record_recommendation_edited_detection() -> None:
    """A committed text differing from the original escalation recommendation is recorded as 'edited'."""
    conv_id = _create_test_conversation()
    original = "Investigate the root cause of the outage."
    tool_output = json.dumps([{"text": json.dumps({"recommendation": original}), "type": "text"}])
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO agent_actions (conversation_id, tool_name, tool_output) VALUES (%s, %s, %s::jsonb)",
                (conv_id, "create_escalation_summary", tool_output),
            )
        conn.commit()
    finally:
        _release_conn(conn)

    edited = "This is a completely different action to take."
    result = record_recommendation(
        issue_id=GLOBEX_ISSUE_ID,
        recommended_text=edited,
        risk_level="high",
        outcome="accepted",
        user_role="admin",
        conversation_id=conv_id,
    )
    assert result.outcome == "edited"

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT recommended_text, final_text FROM agent_recommendations WHERE id = %s",
                (result.id,),
            )
            recommended, final = cur.fetchone()
    finally:
        _release_conn(conn)
    assert recommended == original
    assert final == edited


def test_record_recommendation_permission_sales_user() -> None:
    """record_recommendation raises PermissionError for sales_user."""
    try:
        record_recommendation(
            issue_id=GLOBEX_ISSUE_ID,
            recommended_text="Should not be allowed.",
            risk_level="low",
            outcome="dismissed",
            user_role="sales_user",
            conversation_id="test-conv-id",
        )
    except PermissionError:
        return
    raise AssertionError("expected PermissionError for sales_user")


def test_create_escalation_summary() -> None:
    """create_escalation_summary returns a validated EscalationSummary for support_user."""
    summary = create_escalation_summary(customer_id=GLOBEX_CUSTOMER_ID, user_role="support_user")
    assert isinstance(summary, EscalationSummary)


def run() -> None:
    """Run all checks, printing PASS/FAIL for each."""
    check("get_customer_profile", test_get_customer_profile)
    check("get_customer_profile (not found)", test_get_customer_profile_not_found)
    check("get_customer_profile (prefix match: 'Globex' → 'Globex Corp')", test_get_customer_profile_prefix_match)
    check("get_customer_profile (multi-match: 'Corp' → validation_error)", test_get_customer_profile_multi_match)
    check("get_customer_profile (prefix not found: 'FooBar')", test_get_customer_profile_prefix_not_found)
    check("get_open_issues", test_get_open_issues)
    check("get_issue_detail", test_get_issue_detail)
    check("create_next_action", test_create_next_action)
    check("create_next_action (PermissionError: sales_user)", test_create_next_action_permission_sales_user)
    check("create_next_action (PermissionError: support_user)", test_create_next_action_permission_support_user)
    check("add_issue_update", test_add_issue_update)
    check("add_issue_update (PermissionError: sales_user)", test_add_issue_update_permission_sales_user)
    check("record_recommendation", test_record_recommendation)
    check("record_recommendation (accepted links to next action)", test_record_recommendation_accepted_links)
    check("record_recommendation (edited detected server-side)", test_record_recommendation_edited_detection)
    check("record_recommendation (PermissionError: sales_user)", test_record_recommendation_permission_sales_user)
    check("create_escalation_summary", test_create_escalation_summary)


if __name__ == "__main__":
    run()
