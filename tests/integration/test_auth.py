"""End-to-end check of Keycloak login -> JWT claims -> /auth/me role mapping.

Requires Keycloak running locally on port 8080 with the acme realm imported
(see infra/keycloak/acme-realm.json). Run with:
    python tests/test_auth.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from jose import jwt

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:8080")
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "acme")
KEYCLOAK_CLIENT_ID = os.environ.get("KEYCLOAK_CLIENT_ID", "acme-api")
KEYCLOAK_CLIENT_SECRET = os.environ.get("KEYCLOAK_CLIENT_SECRET", "acme-api-secret")

TOKEN_URL = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"

USER_PASSWORD = "password123"

EXPECTED_ROLES = {
    "alice": "sales_user",
    "bob": "support_user",
    "carol": "admin",
}


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


def run() -> None:
    """Log in as alice, bob, and carol and verify their /auth/me role."""
    api_dir = Path(__file__).resolve().parent.parent.parent / "api"
    sys.path.insert(0, str(api_dir))

    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)

    for username, expected_role in EXPECTED_ROLES.items():
        token = fetch_access_token(username, USER_PASSWORD)

        claims = jwt.get_unverified_claims(token)
        print(f"--- {username} ---")
        print(f"claims: {claims}")

        response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
        body = response.json()
        print(f"/auth/me: {body}")

        assert body["username"] == username, (
            f"expected username '{username}', got '{body['username']}'"
        )
        assert body["role"] == expected_role, (
            f"expected role '{expected_role}' for {username}, got '{body['role']}'"
        )
        print(f"OK: {username} -> {body['role']}\n")


if __name__ == "__main__":
    run()
