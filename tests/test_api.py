"""End-to-end HTTP test of the FastAPI app: chat, customers, issues, and RBAC.

Requires:
  - Keycloak running locally with the acme realm imported (infra/keycloak/acme-realm.json)
  - Postgres reachable via POSTGRES_URL with migrations applied and seed data loaded
    (api/db/migrate.sh, then api/db/seed.py)
  - Redis reachable via REDIS_URL
  - mcp_server/.venv set up with mcp_server/requirements.txt installed
  - LITELLM_URL pointing at a running LiteLLM proxy

Run with:
    python tests/test_api.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:8080")
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "acme")
KEYCLOAK_CLIENT_ID = os.environ.get("KEYCLOAK_CLIENT_ID", "acme-api")
KEYCLOAK_CLIENT_SECRET = os.environ.get("KEYCLOAK_CLIENT_SECRET", "acme-api-secret")

TOKEN_URL = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
USER_PASSWORD = "password123"

GLOBEX_CUSTOMER_ID = "a1000000-0000-0000-0000-000000000001"
PLACEHOLDER_NEXT_ACTION_ID = "00000000-0000-0000-0000-000000000000"


def fetch_access_token(username: str, password: str) -> str:
    """Exchange a username/password for an access token via the password grant."""
    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": KEYCLOAK_CLIENT_ID,
            "client_secret": KEYCLOAK_CLIENT_SECRET,
            "username": username,
            "password": password,
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]


def auth_headers(username: str) -> dict[str, str]:
    """Return an Authorization header carrying a bearer token for username."""
    return {"Authorization": f"Bearer {fetch_access_token(username, USER_PASSWORD)}"}


def run() -> None:
    """Exercise /chat, /customers, /issues, and /next-actions RBAC end-to-end."""
    api_dir = Path(__file__).resolve().parent.parent / "api"
    sys.path.insert(0, str(api_dir))

    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as client:
        carol_headers = auth_headers("carol")
        alice_headers = auth_headers("alice")

        chat_response = client.post(
            "/chat",
            json={"message": "What open issues does Globex Corp have?"},
            headers=carol_headers,
        )
        assert chat_response.status_code == 200, chat_response.text
        chat_body = chat_response.json()
        print(f"/chat: {chat_body}")
        assert "get_open_issues" in chat_body["tools_called"], (
            f"expected 'get_open_issues' in tools_called, got {chat_body['tools_called']}"
        )
        print("OK: POST /chat called get_open_issues\n")

        customers_response = client.get("/customers", headers=carol_headers)
        assert customers_response.status_code == 200, customers_response.text
        customers = customers_response.json()
        assert len(customers) == 3, f"expected 3 customers, got {len(customers)}"
        print(f"OK: GET /customers -> {len(customers)} customers\n")

        issues_response = client.get(
            "/issues", params={"customer_id": GLOBEX_CUSTOMER_ID}, headers=carol_headers
        )
        assert issues_response.status_code == 200, issues_response.text
        issues = issues_response.json()
        assert len(issues) == 3, f"expected 3 issues for Globex Corp, got {len(issues)}"
        print(f"OK: GET /issues?customer_id=<Globex Corp> -> {len(issues)} issues\n")

        forbidden_response = client.patch(
            f"/next-actions/{PLACEHOLDER_NEXT_ACTION_ID}/status",
            json={"status": "completed"},
            headers=alice_headers,
        )
        assert forbidden_response.status_code == 403, forbidden_response.text
        print("OK: PATCH /next-actions/{id}/status as alice (sales_user) -> 403\n")


if __name__ == "__main__":
    run()
