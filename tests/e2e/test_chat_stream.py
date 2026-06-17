"""End-to-end test of the SSE streaming chat endpoint, POST /chat/stream.

Requires:
  - Keycloak running locally with the acme realm imported (infra/keycloak/acme-realm.json)
  - Postgres reachable via POSTGRES_URL with migrations applied and seed data loaded
    (api/db/migrate.sh, then api/db/seed.py)
  - Redis reachable via REDIS_URL
  - mcp_server/.venv set up with mcp_server/requirements.txt installed
  - LITELLM_URL pointing at a running LiteLLM proxy

Run with:
    python tests/test_chat_stream.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

API_URL = os.environ.get("API_URL", "http://localhost:8000")
KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:8080")
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "acme")
KEYCLOAK_CLIENT_ID = os.environ.get("KEYCLOAK_CLIENT_ID", "acme-api")
KEYCLOAK_CLIENT_SECRET = os.environ.get("KEYCLOAK_CLIENT_SECRET", "acme-api-secret")

TOKEN_URL = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
USER_PASSWORD = "password123"


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
    """Stream POST /chat/stream and verify status/token/done framing and persistence."""
    with httpx.Client(base_url=API_URL, timeout=60.0) as client:
        carol_headers = auth_headers("carol")

        statuses: list[str] = []
        tokens: list[str] = []
        done: dict | None = None
        event_type = ""

        with client.stream(
            "POST",
            "/chat/stream",
            json={"message": "What are Globex Corp's open issues and who's the account manager?"},
            headers=carol_headers,
        ) as response:
            assert response.status_code == 200, response.read()
            assert response.headers["content-type"].startswith("text/event-stream")

            for line in response.iter_lines():
                if line.startswith("event: "):
                    event_type = line[len("event: "):].strip()
                    continue
                if not line.startswith("data: "):
                    continue

                data = json.loads(line[len("data: "):])
                print(f"event: {event_type}\ndata: {data}\n")

                if event_type == "status":
                    statuses.append(data["status"])
                elif event_type == "token":
                    tokens.append(data["content"])
                elif event_type == "done":
                    done = data
                elif event_type == "error":
                    raise AssertionError(f"stream returned an error event: {data}")

        assert statuses, "expected at least one status event for a tool-calling question"
        print(f"OK: received {len(statuses)} status event(s): {statuses}\n")

        assert tokens, "expected at least one token event"
        streamed_response = "".join(tokens)
        print(f"OK: received {len(tokens)} token event(s)\n")

        assert done is not None, "expected a done event"
        assert done["response"] == streamed_response, (
            "streamed tokens should reconcile to the same text as the done event's response"
        )
        assert "get_open_issues" in done["tools_called"], (
            f"expected 'get_open_issues' in tools_called, got {done['tools_called']}"
        )
        print(f"OK: done event -> {done}\n")

        history_response = client.get(f"/conversations/{done['conversation_id']}", headers=carol_headers)
        assert history_response.status_code == 200, history_response.text
        turns = history_response.json()["turns"]
        assert turns[-1]["content"] == done["response"], "persisted turn should match the streamed response"
        print(f"OK: GET /conversations/{done['conversation_id']} -> {len(turns)} turns persisted\n")


if __name__ == "__main__":
    run()
