"""LangGraph state shape for the support agent.

Unlike the Pydantic models elsewhere in api/models/, this is a TypedDict:
LangGraph nodes return partial state updates (dicts), and the `messages`
field uses the `add_messages` reducer so that each node's returned messages
are appended to (not replacing) the running conversation history.
"""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel


class AgentState(TypedDict):
    """State threaded through the support agent graph."""

    conversation_id: str
    user_id: str
    user_role: str
    known_entities: str
    messages: Annotated[list[BaseMessage], add_messages]
    final_response: str | None
    total_prompt_tokens: int
    total_completion_tokens: int
    total_cost_usd: float
    model_used: str


class ModelPricing(BaseModel):
    """USD prices per 1M tokens for a single model.

    cached_input_per_1m is the discounted rate for input tokens served from
    the provider's prompt cache; it applies to the cache_read subset of a
    call's input tokens.
    """

    input_per_1m: float
    cached_input_per_1m: float
    output_per_1m: float


class ToolErrorPayload(BaseModel):
    """Structured error returned by an MCP tool's isError result.

    Mirrors mcp_server.models.ToolErrorPayload, the JSON contract that
    _check_role and the not_found/validation_error helpers in
    mcp_server/errors.py encode into a tool's error text.
    """

    error_type: Literal["permission_denied", "not_found", "validation_error", "internal_error"]
    detail: str
