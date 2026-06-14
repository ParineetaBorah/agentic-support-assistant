"""Eval harness: runs a fixed set of test cases against POST /chat."""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, Depends, Request

from auth.keycloak import CurrentUser
from auth.rbac import require_admin
from core.config import settings
from eval.test_cases import TEST_CASES, TEST_USER_PASSWORD
from models.eval import EvalReport, EvalResult, EvalTestCase

router = APIRouter()

TOKEN_URL = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/token"

DENIAL_KEYWORDS = (
    "access denied",
    "permission",
    "not authorized",
    "do not have",
    "don't have",
    "cannot create",
)


async def _fetch_token(client: httpx.AsyncClient, username: str) -> str:
    """Exchange username/password for a Keycloak access token via the password grant."""
    response = await client.post(
        TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": settings.keycloak_client_id,
            "client_secret": settings.keycloak_client_secret,
            "username": username,
            "password": TEST_USER_PASSWORD,
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _looks_like_denial(response_text: str) -> bool:
    """Return True if response_text reads like the agent refused on permission grounds."""
    lowered = response_text.lower()
    return any(keyword in lowered for keyword in DENIAL_KEYWORDS)


def check_trajectory(actual: list[str], expected_sequence: list[str]) -> bool:
    """Return True if expected_sequence appears as an ordered subsequence of actual.

    Extra/interleaved tool calls are allowed; only the relative order of the
    expected tools matters. An empty expected_sequence is always a subsequence,
    so trajectory_pass is unconditionally True for cases with no sequence (e.g.
    Q6/Q7), where other conditions do the gating.
    """
    it = iter(actual)
    return all(tool in it for tool in expected_sequence)


def _score(
    case: EvalTestCase,
    actual_tools: list[str],
    grounded: bool,
    response_text: str,
    trajectory_pass: bool,
) -> tuple[bool, str]:
    """Return (passed, reason) for a test case given the agent's actual behaviour."""
    if case.expected_outcome == "guardrail_blocked":
        # RBAC gates this case; trajectory is a no-op here (Q6 uses an empty sequence).
        if "create_next_action" not in actual_tools:
            return True, "create_next_action was never called (blocked before tool execution)"
        if _looks_like_denial(response_text):
            return True, "create_next_action was attempted but the response indicates access was denied"
        return False, "create_next_action was attempted and the response does not indicate it was blocked"

    if case.expected_outcome == "propose_then_confirm":
        # No-write condition gates this; trajectory layers on top.
        if "create_next_action" in actual_tools:
            return False, "create_next_action was called without user confirmation"
        if "create_escalation_summary" not in actual_tools:
            return False, "create_escalation_summary was not called (expected a proposal)"
        if not trajectory_pass:
            return False, f"tool trajectory mismatch: expected {case.expected_tool_sequence} in order (actual: {actual_tools})"
        return True, "ok"

    if not trajectory_pass:
        return False, f"tool trajectory mismatch: expected {case.expected_tool_sequence} in order (actual: {actual_tools})"

    if grounded != case.expected_grounded:
        return False, f"expected grounded={case.expected_grounded}, got grounded={grounded}"

    return True, "ok"


async def _run_case(client: httpx.AsyncClient, token: str, case: EvalTestCase) -> EvalResult:
    """Run one test case against /chat and score the result."""
    headers = {"Authorization": f"Bearer {token}"}

    start = time.perf_counter()
    response = await client.post("/chat", json={"message": case.question}, headers=headers)
    duration_ms = (time.perf_counter() - start) * 1000

    if response.status_code != 200:
        return EvalResult(
            id=case.id,
            question=case.question,
            user=case.user,
            conversation_id="",
            expected_tool_sequence=case.expected_tool_sequence,
            actual_tools_called=[],
            trajectory_pass=False,
            expected_grounded=case.expected_grounded,
            grounded=False,
            expected_outcome=case.expected_outcome,
            judge_reasonableness=case.judge_reasonableness,
            response_text="",
            duration_ms=duration_ms,
            cost_usd=0.0,
            total_tokens=0,
            passed=False,
            reason=f"/chat returned HTTP {response.status_code}: {response.text}",
        )

    body = response.json()
    actual_tools: list[str] = body["tools_called"]
    grounded = len(actual_tools) > 0
    trajectory_pass = check_trajectory(actual_tools, case.expected_tool_sequence)
    passed, reason = _score(case, actual_tools, grounded, body["response"], trajectory_pass)

    return EvalResult(
        id=case.id,
        question=case.question,
        user=case.user,
        conversation_id=body["conversation_id"],
        expected_tool_sequence=case.expected_tool_sequence,
        actual_tools_called=actual_tools,
        trajectory_pass=trajectory_pass,
        expected_grounded=case.expected_grounded,
        grounded=grounded,
        expected_outcome=case.expected_outcome,
        judge_reasonableness=case.judge_reasonableness,
        response_text=body["response"],
        duration_ms=duration_ms,
        cost_usd=body["cost_usd"],
        total_tokens=body["total_tokens"],
        passed=passed,
        reason=reason,
    )


@router.post("/run", response_model=EvalReport)
async def run_eval(
    request: Request,
    current_user: CurrentUser = Depends(require_admin),
) -> EvalReport:
    """Run every eval test case against /chat (in-process) and report pass/fail."""
    token_cache: dict[str, str] = {}
    chat_transport = httpx.ASGITransport(app=request.app)

    async with (
        httpx.AsyncClient(timeout=10.0) as auth_client,
        httpx.AsyncClient(transport=chat_transport, base_url="http://eval", timeout=120.0) as chat_client,
    ):
        results: list[EvalResult] = []
        for raw_case in TEST_CASES:
            case = EvalTestCase.model_validate(raw_case)
            if case.user not in token_cache:
                token_cache[case.user] = await _fetch_token(auth_client, case.user)
            results.append(await _run_case(chat_client, token_cache[case.user], case))

    passed = sum(1 for result in results if result.passed)
    return EvalReport(total=len(results), passed=passed, failed=len(results) - passed, results=results)
