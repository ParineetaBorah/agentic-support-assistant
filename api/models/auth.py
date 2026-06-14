"""Pydantic models for authentication: JWT claims and API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RealmAccess(BaseModel):
    """The realm_access claim of a Keycloak access token."""

    roles: list[str] = Field(default_factory=list)


class KeycloakClaims(BaseModel):
    """The subset of decoded Keycloak JWT claims used by this API."""

    sub: str
    preferred_username: str
    realm_access: RealmAccess = Field(default_factory=RealmAccess)


class UserOut(BaseModel):
    """Response body describing the authenticated user."""

    username: str
    role: str


class LoginRequest(BaseModel):
    """Request body for POST /auth/login."""

    username: str
    password: str


class LoginResponse(BaseModel):
    """Response body for POST /auth/login."""

    access_token: str
    token_type: str
    expires_in: int
    username: str
    role: str


class KeycloakTokenResponse(BaseModel):
    """The token endpoint response returned by Keycloak on a successful grant."""

    access_token: str
    token_type: str
    expires_in: int
