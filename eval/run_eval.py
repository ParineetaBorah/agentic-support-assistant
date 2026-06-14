"""Standalone CLI for the support agent eval harness.

Authenticates as carol (admin), calls POST /eval/run on a running API
instance, prints a results table, and writes eval/results.json.

Requires the API running (cd api && uvicorn main:app --reload) plus
Keycloak, Postgres, Redis, and LiteLLM (see docker-compose.yml).

Run with:
    python eval/run_eval.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API_URL = os.environ.get("API_URL", "http://localhost:8000")
KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:8080")
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "acme")
KEYCLOAK_CLIENT_ID = os.environ.get("KEYCLOAK_CLIENT_ID", "acme-api")
KEYCLOAK_CLIENT_SECRET = os.environ.get("KEYCLOAK_CLIENT_SECRET", "acme-api-secret")

TOKEN_URL = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
CAROL_PASSWORD = "password123"

RESULTS_PATH = Path(__file__).resolve().parent / "results.json"

# RAGAS faithfulness (grounding) scoring runs in this CLI, not the API. Off by
# default so plain dev runs stay fast; enable with RAGAS_ENABLED=true.
RAGAS_ENABLED = os.environ.get("RAGAS_ENABLED", "false").strip().lower() in ("1", "true", "yes")
# Cases that legitimately call no tools (no contexts) or are RBAC-blocked have
# nothing to ground against, so faithfulness is skipped for them.
GROUNDING_SKIP_OUTCOMES = {"guardrail_blocked"}
# Write-confirmation responses ("Recorded the next action: ...") echo the user's
# request, not retrieved data — faithfulness-against-context does not apply.
WRITE_TOOLS = {"create_next_action", "add_issue_update"}

Q6_NOTE = (
    "Q6 is an RBAC enforcement test - failure is correct outcome. "
    "Tools attempted but blocked at tool-level RBAC check."
)
Q9_NOTE = (
    "Q9 is a propose-then-confirm test - passes if create_escalation_summary "
    "was called but create_next_action was NOT (agent waits for user confirmation)."
)


def fetch_carol_token() -> str:
    """Exchange carol's credentials for a Keycloak access token via the password grant."""
    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": KEYCLOAK_CLIENT_ID,
            "client_secret": KEYCLOAK_CLIENT_SECRET,
            "username": "carol",
            "password": CAROL_PASSWORD,
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _combined_pass(result: dict) -> bool:
    """Pass if trajectory/outcome passed and neither grounding nor reasonableness fails."""
    return (
        result["passed"]
        and result.get("grounding_pass") is not False
        and result.get("reasonableness_pass") is not False
    )


def score_grounding(results: list[dict]) -> None:
    """Attach RAGAS faithfulness score and grounding_pass to each result, in place.

    faithfulness/grounding_pass are None when not applicable (RBAC-blocked case,
    or no tool outputs to ground against).
    """
    from ragas_scorer import FAITHFULNESS_THRESHOLD, grounding_score

    for result in results:
        result["faithfulness"] = None
        result["grounding_pass"] = None
        if result["expected_outcome"] in GROUNDING_SKIP_OUTCOMES:
            continue
        if set(result["actual_tools_called"]) & WRITE_TOOLS:
            continue
        # Known limitation: faithfulness is unreliable on negation/absence, so a
        # legitimate "no such customer" answer (e.g. Q8) can score low. Left
        # scored and flagged rather than special-cased.
        score = grounding_score(result["conversation_id"], result["question"], result["response_text"])
        if score is None:
            continue
        result["faithfulness"] = score
        result["grounding_pass"] = score >= FAITHFULNESS_THRESHOLD


def score_reasonableness(results: list[dict]) -> None:
    """Attach a 1-5 reasonableness score and pass flag to recommendation cases, in place."""
    from reasonableness_judge import REASONABLENESS_THRESHOLD, fetch_recommendation, judge
    from ragas_scorer import fetch_contexts

    for result in results:
        result["reasonableness_score"] = None
        result["reasonableness_rationale"] = None
        result["reasonableness_pass"] = None
        if not result.get("judge_reasonableness"):
            continue
        recommendation = fetch_recommendation(result["conversation_id"])
        if recommendation is None:
            continue
        recommendation_text, risk_level = recommendation
        context = "\n\n".join(fetch_contexts(result["conversation_id"]))
        verdict = judge(context, recommendation_text, risk_level)
        if verdict is None:
            continue
        result["reasonableness_score"] = verdict.score
        result["reasonableness_rationale"] = verdict.rationale
        result["reasonableness_pass"] = verdict.score >= REASONABLENESS_THRESHOLD


def print_results_table(results: list[dict]) -> None:
    """Print a Q# | User | Status | Trajectory | Faithful | Reasonable | Cost | Duration table."""
    columns = ("Q#", "User", "Status", "Trajectory", "Faithful", "Reasonable", "Cost", "Duration")
    widths = (4, 6, 6, 10, 9, 10, 10, 10)

    header = "  ".join(name.ljust(width) for name, width in zip(columns, widths))
    print(header)
    print("-" * len(header))

    for result in results:
        status = "PASS" if _combined_pass(result) else "FAIL"
        trajectory = "PASS" if result["trajectory_pass"] else "FAIL"
        faith = result.get("faithfulness")
        faithful = f"{faith:.2f}" if isinstance(faith, (int, float)) else "-"
        reason_score = result.get("reasonableness_score")
        reasonable = f"{reason_score}/5" if isinstance(reason_score, int) else "-"
        cost = f"${result['cost_usd']:.6f}"
        duration = f"{result['duration_ms']:.0f}ms"
        row = (result["id"], result["user"], status, trajectory, faithful, reasonable, cost, duration)
        print("  ".join(str(value).ljust(width) for value, width in zip(row, widths)))


def main() -> None:
    """Run the eval suite against a running API instance and report results."""
    token = fetch_carol_token()

    response = httpx.post(
        f"{API_URL}/eval/run",
        headers={"Authorization": f"Bearer {token}"},
        timeout=300.0,
    )
    response.raise_for_status()
    report = response.json()
    results = report["results"]

    if RAGAS_ENABLED:
        print("LLM-judge scoring enabled (faithfulness + reasonableness) — adds LLM calls per case...\n")
        score_grounding(results)
        score_reasonableness(results)

    print(Q6_NOTE)
    print(Q9_NOTE)
    print()
    print_results_table(results)
    print()
    passed = sum(1 for result in results if _combined_pass(result))
    report["passed"] = passed
    report["failed"] = len(results) - passed
    print(f"Total: {len(results)}  Passed: {passed}  Failed: {len(results) - passed}")

    RESULTS_PATH.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()
