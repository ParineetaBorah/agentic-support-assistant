"""FastAPI dependency for authenticating requests against Keycloak."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import JOSEError
from pydantic import ValidationError

from core.config import settings
from core.resilience import HTTP_TIMEOUT, transient_http_retry
from models.auth import KeycloakClaims

JWKS_URL = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
JWKS_CACHE_TTL_SECONDS = 300

JWT_ALGORITHMS = ["RS256"]

ROLES_MOST_TO_LEAST_PRIVILEGED = ["admin", "support_user", "sales_user"]

_jwks_cache: dict[str, Any] = {"keys": None, "fetched_at": 0.0}

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    """Authenticated principal resolved from a validated Keycloak JWT."""

    user_id: str
    username: str
    role: str


@transient_http_retry
async def _fetch_jwks() -> dict[str, Any]:
    """Fetch Keycloak's JWKS, retrying transient network failures with backoff."""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        response = await client.get(JWKS_URL)
        response.raise_for_status()
        return response.json()


async def _get_jwks() -> dict[str, Any]:
    """Return Keycloak's JWKS, refreshing the cache if its TTL has elapsed."""
    now = time.monotonic()
    if _jwks_cache["keys"] is None or now - _jwks_cache["fetched_at"] > JWKS_CACHE_TTL_SECONDS:
        _jwks_cache["keys"] = await _fetch_jwks()
        _jwks_cache["fetched_at"] = now
    return _jwks_cache["keys"]


def select_role(roles: list[str]) -> str | None:
    """Return the highest-privilege role from roles, or None if none are recognised."""
    for candidate in ROLES_MOST_TO_LEAST_PRIVILEGED:
        if candidate in roles:
            return candidate
    return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    """Resolve the authenticated user from the request's Bearer token.

    Raises HTTP 401 if the token is missing, malformed, unsigned by a known
    Keycloak key, expired, issued for the wrong audience, or missing required
    claims. Raises HTTP 403 if the token's realm roles contain none of
    ROLES_MOST_TO_LEAST_PRIVILEGED.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        unverified_header = jwt.get_unverified_header(token)
    except JOSEError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token header",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    jwks = await _get_jwks()
    signing_key = next(
        (key for key in jwks.get("keys", []) if key.get("kid") == unverified_header.get("kid")),
        None,
    )
    if signing_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to find matching signing key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=JWT_ALGORITHMS,
            audience=settings.keycloak_client_id,
        )
    except JOSEError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        parsed_claims = KeycloakClaims.model_validate(claims)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing required claims",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    role = select_role(parsed_claims.realm_access.roles)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No recognised role assigned to this user",
        )

    return CurrentUser(
        user_id=parsed_claims.sub,
        username=parsed_claims.preferred_username,
        role=role,
    )
