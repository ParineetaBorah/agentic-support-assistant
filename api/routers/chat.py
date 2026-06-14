"""Chat endpoints: run the support agent and persist the conversation."""

from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from agent.graph import build_graph
from agent.mcp_client import get_mcp_tools
from auth.keycloak import CurrentUser
from auth.rbac import require_sales_or_above
from core.redis import get_conversation_history, save_conversation_turn
from db.conversations import (
    create_conversation,
    get_conversation,
    insert_agent_action,
    insert_conversation_turn,
    list_conversation_turns,
)
from db.pool import get_db
from models.agent import AgentState
from models.chat import ChatRequest, ChatResponse, ChatStreamError, ChatStreamStatus, ChatStreamToken

router = APIRouter()

TOOL_STATUS_MESSAGES = {
    "get_customer_profile": "Looking up customer details...",
    "get_open_issues": "Checking open issues...",
    "get_issue_detail": "Pulling up issue details...",
    "create_next_action": "Recording the next action...",
    "create_escalation_summary": "Preparing an escalation summary...",
    "add_issue_update": "Logging the issue update...",
    "record_recommendation": "Recording the recommendation outcome...",
}

# Caps the agent's reason/act loop (each tool call is ~2 steps). Bounds runaway
# retries on repeated tool failures; well above any legitimate multi-tool flow.
AGENT_RECURSION_LIMIT = 18


def _history_to_message(turn: dict) -> BaseMessage:
    """Convert a cached/persisted conversation turn into a chat message."""
    if turn["role"] == "user":
        return HumanMessage(content=turn["content"])
    return AIMessage(content=turn["content"])


def _sse(event: str, payload: BaseModel) -> str:
    """Format a Pydantic model as a single Server-Sent Events frame."""
    return f"event: {event}\ndata: {payload.model_dump_json()}\n\n"


async def _prepare_chat_state(
    body: ChatRequest, conn: asyncpg.Connection, current_user: CurrentUser
) -> tuple[str, list[dict], AgentState]:
    """Resolve the conversation and build the initial agent state for a chat turn."""
    if body.conversation_id is None:
        conversation_row = await create_conversation(conn, current_user.user_id)
        conversation_id = str(conversation_row["id"])
    else:
        conversation_id = body.conversation_id
        if await get_conversation(conn, conversation_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    history = await get_conversation_history(conversation_id)
    if not history:
        history = [
            {"role": row["role"], "content": row["content"]}
            for row in await list_conversation_turns(conn, conversation_id)
        ]

    initial_messages = [_history_to_message(turn) for turn in history]
    initial_messages.append(HumanMessage(content=body.message))

    initial_state: AgentState = {
        "conversation_id": conversation_id,
        "user_id": current_user.user_id,
        "user_role": current_user.role,
        "messages": initial_messages,
        "final_response": None,
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_cost_usd": 0.0,
        "model_used": "",
    }
    return conversation_id, history, initial_state


async def _persist_turn(
    conn: asyncpg.Connection,
    conversation_id: str,
    user_message: str,
    new_messages: list[BaseMessage],
    *,
    total_prompt_tokens: int,
    total_completion_tokens: int,
    total_cost_usd: float,
    model_used: str,
    final_response: str | None,
    history_len: int,
) -> ChatResponse:
    """Persist a user/assistant turn and its tool calls, returning the chat summary."""
    tool_calls = [
        tool_call
        for message in new_messages
        if isinstance(message, AIMessage)
        for tool_call in message.tool_calls
    ]
    tool_outputs = {
        message.tool_call_id: message.content for message in new_messages if isinstance(message, ToolMessage)
    }

    response_text = final_response or ""
    total_tokens = total_prompt_tokens + total_completion_tokens

    await insert_conversation_turn(conn, conversation_id, "user", user_message)
    assistant_turn = await insert_conversation_turn(
        conn,
        conversation_id,
        "assistant",
        response_text,
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        total_tokens=total_tokens,
        cost_usd=total_cost_usd,
        model_used=model_used or None,
    )

    for tool_call in tool_calls:
        await insert_agent_action(
            conn,
            conversation_id,
            str(assistant_turn["id"]),
            tool_call["name"],
            tool_call["args"],
            tool_outputs.get(tool_call["id"], ""),
        )

    await save_conversation_turn(conversation_id, "user", user_message)
    await save_conversation_turn(conversation_id, "assistant", response_text)

    return ChatResponse(
        response=response_text,
        conversation_id=conversation_id,
        tools_called=[tool_call["name"] for tool_call in tool_calls],
        turn_count=history_len + 2,
        cost_usd=total_cost_usd,
        total_tokens=total_tokens,
    )


@router.post("", response_model=ChatResponse)
async def post_chat(
    body: ChatRequest,
    conn: asyncpg.Connection = Depends(get_db),
    current_user: CurrentUser = Depends(require_sales_or_above),
) -> ChatResponse:
    """Run the support agent on a message and persist the resulting turn."""
    conversation_id, history, initial_state = await _prepare_chat_state(body, conn, current_user)

    async with get_mcp_tools() as tools:
        graph = build_graph(tools)
        result = await graph.ainvoke(initial_state, config={"recursion_limit": AGENT_RECURSION_LIMIT})

    new_messages = result["messages"][len(initial_state["messages"]):]

    return await _persist_turn(
        conn,
        conversation_id,
        body.message,
        new_messages,
        total_prompt_tokens=result["total_prompt_tokens"],
        total_completion_tokens=result["total_completion_tokens"],
        total_cost_usd=result["total_cost_usd"],
        model_used=result["model_used"],
        final_response=result["final_response"],
        history_len=len(history),
    )


@router.post("/stream")
async def post_chat_stream(
    body: ChatRequest,
    conn: asyncpg.Connection = Depends(get_db),
    current_user: CurrentUser = Depends(require_sales_or_above),
) -> StreamingResponse:
    """Run the support agent and stream tool-status and answer tokens as Server-Sent Events."""
    conversation_id, history, initial_state = await _prepare_chat_state(body, conn, current_user)

    async def event_stream() -> AsyncIterator[str]:
        new_messages: list[BaseMessage] = []
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_cost_usd = 0.0
        model_used = ""
        final_response: str | None = None

        try:
            async with get_mcp_tools() as tools:
                graph = build_graph(tools)
                async for mode, chunk in graph.astream(
                    initial_state,
                    stream_mode=["updates", "messages"],
                    config={"recursion_limit": AGENT_RECURSION_LIMIT},
                ):
                    if mode == "messages":
                        message_chunk, chunk_metadata = chunk
                        if chunk_metadata.get("langgraph_node") == "agent" and message_chunk.content:
                            yield _sse("token", ChatStreamToken(content=message_chunk.content))
                    elif mode == "updates":
                        if "agent" in chunk:
                            output = chunk["agent"]
                            new_messages.extend(output["messages"])
                            total_prompt_tokens = output["total_prompt_tokens"]
                            total_completion_tokens = output["total_completion_tokens"]
                            total_cost_usd = output["total_cost_usd"]
                            model_used = output["model_used"]
                            if output.get("final_response") is not None:
                                final_response = output["final_response"]
                            for tool_call in output["messages"][0].tool_calls:
                                status_text = TOOL_STATUS_MESSAGES.get(
                                    tool_call["name"], f"Running {tool_call['name']}..."
                                )
                                yield _sse("status", ChatStreamStatus(status=status_text))
                        elif "tools" in chunk:
                            new_messages.extend(chunk["tools"]["messages"])
        except Exception:
            # The response has already started streaming with a 200 status, so any
            # failure here must become an in-band "error" event, not an HTTP error.
            yield _sse("error", ChatStreamError(message="Something went wrong reaching the agent."))
            return

        chat_response = await _persist_turn(
            conn,
            conversation_id,
            body.message,
            new_messages,
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
            total_cost_usd=total_cost_usd,
            model_used=model_used,
            final_response=final_response,
            history_len=len(history),
        )
        yield _sse("done", chat_response)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
