"""Authentication-related endpoints."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt

from auth.keycloak import CurrentUser, get_current_user, select_role
from core.config import settings
from models.auth import KeycloakClaims, KeycloakTokenResponse, LoginRequest, LoginResponse, UserOut

router = APIRouter()

TOKEN_URL = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/token"


@router.get("/me", response_model=UserOut)
async def read_current_user(
    current_user: CurrentUser = Depends(get_current_user),
) -> UserOut:
    """Return the authenticated user's username and role."""
    return UserOut(username=current_user.username, role=current_user.role)


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    """Exchange a username and password for an access token via Keycloak.

    The Keycloak client secret is used only here, server-side; browser code
    never talks to Keycloak directly.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "password",
                "client_id": settings.keycloak_client_id,
                "client_secret": settings.keycloak_client_secret,
                "username": body.username,
                "password": body.password,
            },
        )

    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    response.raise_for_status()

    token = KeycloakTokenResponse.model_validate(response.json())
    claims = KeycloakClaims.model_validate(jwt.get_unverified_claims(token.access_token))

    role = select_role(claims.realm_access.roles)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No recognised role assigned to this user",
        )

    return LoginResponse(
        access_token=token.access_token,
        token_type=token.token_type,
        expires_in=token.expires_in,
        username=claims.preferred_username,
        role=role,
    )
