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


def print_results_table(results: list[dict]) -> None:
    """Print a Q# | User | Status | Tools | Cost | Duration table."""
    columns = ("Q#", "User", "Status", "Tools", "Cost", "Duration")
    widths = (4, 6, 6, 45, 10, 10)

    header = "  ".join(name.ljust(width) for name, width in zip(columns, widths))
    print(header)
    print("-" * len(header))

    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        tools = ", ".join(result["actual_tools_called"]) or "-"
        cost = f"${result['cost_usd']:.6f}"
        duration = f"{result['duration_ms']:.0f}ms"
        row = (result["id"], result["user"], status, tools, cost, duration)
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

    print(Q6_NOTE)
    print(Q9_NOTE)
    print()
    print_results_table(report["results"])
    print()
    print(f"Total: {report['total']}  Passed: {report['passed']}  Failed: {report['failed']}")

    RESULTS_PATH.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()
