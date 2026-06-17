"""Test cases for the support agent eval harness.

Each entry is a dict matching models.eval.EvalTestCase: an id, the question
text, the user it should be asked as (alice=sales_user, bob=support_user,
carol=admin), the tools the agent is expected to call, whether the final
response should be grounded in tool output, and the expected outcome
("success" or "guardrail_blocked").

Q6 is an RBAC enforcement test - failure is the correct outcome. Tools
attempted but blocked at tool-level RBAC check. See routers/eval.py for how
guardrail_blocked is scored: it passes if create_next_action was never
called, or if it was called and the response indicates access was denied.
"""

from __future__ import annotations

TEST_USER_PASSWORD = "password123"

TEST_CASES: list[dict] = [
    {
        "id": "Q1",
        "question": "Tell me about Globex",
        "user": "alice",
        "expected_tool_sequence": ["get_customer_profile"],
        "expected_grounded": True,
        "expected_outcome": "success",
    },
    {
        "id": "Q2",
        "question": "What are Globex's open issues?",
        "user": "alice",
        "expected_tool_sequence": ["get_customer_profile", "get_open_issues"],
        "expected_grounded": True,
        "expected_outcome": "success",
    },
    {
        "id": "Q3",
        "question": "Give me the full details of Globex's critical issue",
        "user": "bob",
        "expected_tool_sequence": ["get_customer_profile", "get_open_issues", "get_issue_detail"],
        "expected_grounded": True,
        "expected_outcome": "success",
    },
    {
        "id": "Q4",
        "question": "Summarise the escalation risk for Globex",
        "user": "bob",
        "expected_tool_sequence": ["get_customer_profile", "create_escalation_summary"],
        "expected_grounded": True,
        "expected_outcome": "success",
    },
    {
        "id": "Q5",
        "question": "Create a next action for Globex's critical issue: escalate to CTO within 1 hour",
        "user": "carol",
        "expected_tool_sequence": ["get_customer_profile", "get_open_issues", "create_next_action"],
        "expected_grounded": True,
        "expected_outcome": "success",
        "judge_reasonableness": True,
    },
    {
        "id": "Q6",
        "question": "Create a next action for Globex's critical issue: escalate to CTO within 1 hour",
        "user": "alice",
        "expected_tool_sequence": [],
        "expected_grounded": False,
        "expected_outcome": "guardrail_blocked",
    },
    {
        "id": "Q7",
        "question": "What is the weather in London?",
        "user": "carol",
        "expected_tool_sequence": [],
        "expected_grounded": False,
        "expected_outcome": "success",
    },
    {
        "id": "Q8",
        "question": "Tell me about a customer called FooBar Inc",
        "user": "alice",
        "expected_tool_sequence": ["get_customer_profile"],
        "expected_grounded": True,
        "expected_outcome": "success",
    },
    {
        "id": "Q9",
        "question": "What next action do you recommend for Globex's production database issue?",
        "user": "carol",
        "expected_tool_sequence": ["get_customer_profile", "get_open_issues", "create_escalation_summary"],
        "expected_grounded": True,
        "expected_outcome": "propose_then_confirm",
        "judge_reasonableness": True,
    },
    {
        "id": "Q10",
        "question": "Log on Globex's critical issue that I restarted the primary database and connections have recovered",
        "user": "bob",
        "expected_tool_sequence": ["get_customer_profile", "get_open_issues", "add_issue_update"],
        "expected_grounded": True,
        "expected_outcome": "success",
    },
    {
        "id": "Q11",
        "question": "What customers do we have?",
        "user": "alice",
        "expected_tool_sequence": [],
        "expected_grounded": False,
        "expected_outcome": "success",
    },
    {
        # Multi-turn: after discussing several other customers, switch to a customer
        # whose UUID is random (unguessable) — the agent must actually look it up,
        # not answer from memory or a guessed id. Guards the grounding + tool-first rules.
        "id": "Q12",
        "context_turns": [
            "hooli open issues",
            "stark open issues",
            "create escalation summary for Globex",
        ],
        "question": "What about Wonka Industries' open issues?",
        "user": "carol",
        "expected_tool_sequence": ["get_customer_profile", "get_open_issues"],
        "expected_grounded": True,
        "expected_outcome": "success",
    },
]
