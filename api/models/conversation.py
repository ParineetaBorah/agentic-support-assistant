"""Pydantic models for conversation history."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ConversationTurnOut(BaseModel):
    """A single user or assistant turn in a conversation."""

    role: str
    content: str
    created_at: datetime
    tools_called: list[str] = []


class ConversationHistoryOut(BaseModel):
    """A conversation's turns, oldest first."""

    conversation_id: str
    turns: list[ConversationTurnOut]


class ConversationSummary(BaseModel):
    """Summary of a conversation for display in a conversation list."""

    id: str
    started_at: datetime
    last_turn_at: datetime
    turn_count: int
    preview: str
