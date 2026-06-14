"""Usage and cost tracking endpoints."""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from auth.keycloak import CurrentUser
from auth.rbac import require_admin, require_sales_or_above
from db.conversations import get_conversation
from db.pool import get_db
from db.usage import get_conversation_usage_turns, get_usage_summary, get_user_usage
from models.usage import (
    ConversationTurnUsage,
    ConversationUsage,
    ModelUsage,
    UsageSummary,
    UserUsage,
)

router = APIRouter()


@router.get("/conversation/{conversation_id}", response_model=ConversationUsage)
async def get_conversation_usage(
    conversation_id: str,
    conn: asyncpg.Connection = Depends(get_db),
    current_user: CurrentUser = Depends(require_sales_or_above),
) -> ConversationUsage:
    """Return a per-turn cost and token breakdown for a conversation."""
    conversation_row = await get_conversation(conn, conversation_id)
    if conversation_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    turn_rows = await get_conversation_usage_turns(conn, conversation_id)
    turns = [
        ConversationTurnUsage(
            id=str(row["id"]),
            role=row["role"],
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
            total_tokens=row["total_tokens"],
            cost_usd=float(row["cost_usd"]) if row["cost_usd"] is not None else None,
            model_used=row["model_used"],
            created_at=row["created_at"],
        )
        for row in turn_rows
    ]
    return ConversationUsage(
        conversation_id=conversation_id,
        turns=turns,
        total_cost_usd=sum(turn.cost_usd or 0.0 for turn in turns),
        total_tokens=sum(turn.total_tokens or 0 for turn in turns),
    )


@router.get("/user/{user_id}", response_model=UserUsage)
async def get_usage_for_user(
    user_id: str,
    conn: asyncpg.Connection = Depends(get_db),
    current_user: CurrentUser = Depends(require_admin),
) -> UserUsage:
    """Return total cost and tokens across all of a user's conversations."""
    row = await get_user_usage(conn, user_id)
    return UserUsage(
        user_id=user_id,
        conversation_count=row["conversation_count"],
        total_cost_usd=float(row["total_cost_usd"]),
        total_tokens=int(row["total_tokens"]),
    )


@router.get("/summary", response_model=UsageSummary)
async def get_usage_summary_totals(
    conn: asyncpg.Connection = Depends(get_db),
    current_user: CurrentUser = Depends(require_admin),
) -> UsageSummary:
    """Return usage totals grouped by model_used."""
    rows = await get_usage_summary(conn)
    return UsageSummary(
        models=[
            ModelUsage(
                model_used=row["model_used"],
                call_count=row["call_count"],
                total_cost_usd=float(row["total_cost_usd"]),
                total_tokens=int(row["total_tokens"]),
            )
            for row in rows
        ]
    )
