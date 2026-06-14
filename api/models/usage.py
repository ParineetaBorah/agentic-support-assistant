"""Pydantic models for usage tracking endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ConversationTurnUsage(BaseModel):
    """Usage and cost for a single conversation turn."""

    id: str
    role: str
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cost_usd: float | None
    model_used: str | None
    created_at: datetime


class ConversationUsage(BaseModel):
    """Per-turn usage breakdown for a conversation, plus its totals."""

    conversation_id: str
    turns: list[ConversationTurnUsage]
    total_cost_usd: float
    total_tokens: int


class UserUsage(BaseModel):
    """Total usage across all of a user's conversations."""

    user_id: str
    conversation_count: int
    total_cost_usd: float
    total_tokens: int


class ModelUsage(BaseModel):
    """Aggregate usage for a single model."""

    model_used: str
    call_count: int
    total_cost_usd: float
    total_tokens: int


class UsageSummary(BaseModel):
    """Usage totals grouped by model."""

    models: list[ModelUsage]
