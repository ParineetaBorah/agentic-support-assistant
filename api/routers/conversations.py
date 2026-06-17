"""Conversation history endpoint."""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from auth.keycloak import CurrentUser
from auth.rbac import require_sales_or_above
from db.conversations import get_conversation, list_conversation_turns, list_conversations
from db.pool import get_db
from models.conversation import ConversationHistoryOut, ConversationSummary, ConversationTurnOut

router = APIRouter()


@router.get("", response_model=list[ConversationSummary])
async def read_conversations(
    conn: asyncpg.Connection = Depends(get_db),
    current_user: CurrentUser = Depends(require_sales_or_above),
) -> list[ConversationSummary]:
    """Return the caller's 50 most recent conversations, most recently active first."""
    rows = await list_conversations(conn, current_user.user_id)
    return [
        ConversationSummary(
            id=str(row["id"]),
            started_at=row["started_at"],
            last_turn_at=row["last_turn_at"],
            turn_count=row["turn_count"],
            preview=row["preview"] or "",
        )
        for row in rows
    ]


@router.get("/{conversation_id}", response_model=ConversationHistoryOut)
async def read_conversation_history(
    conversation_id: str,
    conn: asyncpg.Connection = Depends(get_db),
    current_user: CurrentUser = Depends(require_sales_or_above),
) -> ConversationHistoryOut:
    """Return a conversation's turns, oldest first, if it belongs to the caller."""
    conversation = await get_conversation(conn, conversation_id)
    if conversation is None or str(conversation["user_id"]) != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    turns = await list_conversation_turns(conn, conversation_id)
    return ConversationHistoryOut(
        conversation_id=conversation_id,
        turns=[
            ConversationTurnOut(
                role=turn["role"],
                content=turn["content"],
                created_at=turn["created_at"],
                tools_called=turn["tools_called"],
            )
            for turn in turns
        ],
    )
