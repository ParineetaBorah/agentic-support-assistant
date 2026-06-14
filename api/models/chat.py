"""Pydantic models for the chat endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Request body for POST /chat."""

    message: str
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    """Response body for POST /chat."""

    response: str
    conversation_id: str
    tools_called: list[str]
    turn_count: int
    cost_usd: float
    total_tokens: int


class ChatStreamStatus(BaseModel):
    """SSE 'status' event payload for POST /chat/stream: agent progress update."""

    status: str


class ChatStreamToken(BaseModel):
    """SSE 'token' event payload for POST /chat/stream: a chunk of response text."""

    content: str


class ChatStreamError(BaseModel):
    """SSE 'error' event payload for POST /chat/stream: a user-facing error message."""

    message: str
