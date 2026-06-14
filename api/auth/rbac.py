"""FastAPI dependencies enforcing minimum-role access on top of get_current_user."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from auth.keycloak import CurrentUser, get_current_user

ROLE_RANKS = {
    "sales_user": 0,
    "support_user": 1,
    "admin": 2,
}


async def require_sales_or_above(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Allow sales_user, support_user, or admin; reject any unrecognised role."""
    if ROLE_RANKS[current_user.role] < ROLE_RANKS["sales_user"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires role 'sales_user' or higher, but user has role '{current_user.role}'",
        )
    return current_user


async def require_support_or_above(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Allow support_user or admin; reject sales_user and any unrecognised role."""
    if ROLE_RANKS[current_user.role] < ROLE_RANKS["support_user"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires role 'support_user' or higher, but user has role '{current_user.role}'",
        )
    return current_user


async def require_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Allow only admin; reject support_user, sales_user, and any unrecognised role."""
    if ROLE_RANKS[current_user.role] < ROLE_RANKS["admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires role 'admin' or higher, but user has role '{current_user.role}'",
        )
    return current_user
