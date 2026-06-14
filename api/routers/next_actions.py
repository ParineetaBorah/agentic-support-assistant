"""Next-action endpoints."""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from auth.keycloak import CurrentUser
from auth.rbac import require_admin, require_sales_or_above
from db.next_actions import get_next_action, list_next_actions, update_next_action_status
from db.pool import get_db
from models.next_action import NextActionOut, NextActionStatusUpdate

router = APIRouter()


def _to_next_action_out(row: asyncpg.Record) -> NextActionOut:
    """Build a NextActionOut from a next_actions row."""
    return NextActionOut(
        id=str(row["id"]),
        issue_id=str(row["issue_id"]),
        recommendation_text=row["recommendation_text"],
        risk_level=row["risk_level"],
        created_by=str(row["created_by"]),
        status=row["status"],
        created_at=row["created_at"],
    )


@router.get("", response_model=list[NextActionOut])
async def get_next_actions(
    conn: asyncpg.Connection = Depends(get_db),
    current_user: CurrentUser = Depends(require_sales_or_above),
) -> list[NextActionOut]:
    """List all next actions, most recent first."""
    rows = await list_next_actions(conn)
    return [_to_next_action_out(row) for row in rows]


@router.patch("/{next_action_id}/status", response_model=NextActionOut)
async def patch_next_action_status(
    next_action_id: str,
    body: NextActionStatusUpdate,
    conn: asyncpg.Connection = Depends(get_db),
    current_user: CurrentUser = Depends(require_admin),
) -> NextActionOut:
    """Mark a next action as completed."""
    existing = await get_next_action(conn, next_action_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Next action not found")

    row = await update_next_action_status(conn, next_action_id, body.status)
    return _to_next_action_out(row)
