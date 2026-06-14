"""Standalone test of the LangGraph support agent against MCP tools.

Requires:
  - Postgres reachable via POSTGRES_URL with migrations applied and seed
    data loaded (api/db/migrate.sh)
  - mcp_server/server.py running and reachable via MCP_SERVER_URL
  - LITELLM_URL pointing at a running LiteLLM proxy

Run with:
    python tests/test_agent.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402

from agent.errors import parse_tool_error  # noqa: E402
from agent.graph import NO_GROUNDING_RESPONSE, build_graph  # noqa: E402
from agent.mcp_client import get_mcp_tools  # noqa: E402
from models.agent import AgentState  # noqa: E402

CAROL_USER_ID = "b1000000-0000-0000-0000-000000000003"
CAROL_ROLE = "admin"
QUERY = "What are the open issues for Globex Corp?"
GLOBEX_ISSUE_ID = "c1000000-0000-0000-0000-000000000001"


async def run_agent(query: str) -> AgentState:
    """Run the support agent on a single query and return the final state."""
    async with get_mcp_tools() as tools:
        graph = build_graph(tools)
        initial_state: AgentState = {
            "conversation_id": "test-conversation",
            "user_id": CAROL_USER_ID,
            "user_role": CAROL_ROLE,
            "messages": [HumanMessage(content=query)],
            "final_response": None,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_cost_usd": 0.0,
            "model_used": "",
        }
        return await graph.ainvoke(initial_state)


def print_message_trace(state: AgentState) -> None:
    """Print every message in the final state, in order, plus the final response."""
    for message in state["messages"]:
        if isinstance(message, AIMessage) and message.tool_calls:
            calls = ", ".join(f"{c['name']}({c['args']})" for c in message.tool_calls)
            print(f"{message.type}: [tool calls: {calls}]")
        else:
            print(f"{message.type}: {message.content}")
    print(f"final_response: {state['final_response']}")


async def check_structured_permission_error() -> None:
    """create_next_action as sales_user returns a structured permission_denied error."""
    async with get_mcp_tools() as tools:
        tool = next(t for t in tools if t.name == "create_next_action")
        result = await tool.ainvoke(
            {
                "name": "create_next_action",
                "args": {
                    "issue_id": GLOBEX_ISSUE_ID,
                    "recommendation_text": "Should not be allowed.",
                    "risk_level": "low",
                    "user_id": CAROL_USER_ID,
                    "user_role": "sales_user",
                },
                "id": "test-permission-check",
                "type": "tool_call",
            }
        )

    payload = parse_tool_error(result.content)
    if payload is not None and payload.error_type == "permission_denied":
        print("PASS: permission error is structured (error_type=permission_denied)")
    else:
        print(f"FAIL: permission error is structured -> status={result.status!r} content={result.content!r}")


async def main() -> None:
    """Run the agent on a sample query and check the response is tool-grounded."""
    await check_structured_permission_error()

    state = await run_agent(QUERY)
    print_message_trace(state)

    tool_messages = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    if tool_messages:
        print("PASS: at least one tool was called")
    else:
        print("FAIL: at least one tool was called -> no ToolMessage in trace")

    if tool_messages and state["final_response"] != NO_GROUNDING_RESPONSE:
        print("PASS: final response is grounded in tool output")
    else:
        print(f"FAIL: final response is grounded in tool output -> {state['final_response']!r}")


if __name__ == "__main__":
    asyncio.run(main())
