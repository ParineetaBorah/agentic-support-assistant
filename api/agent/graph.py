"""LangGraph support agent that calls Acme's MCP tools."""

from __future__ import annotations

import httpx
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent.errors import parse_tool_error
from core.config import settings
from models.agent import AgentState, ToolErrorPayload

SYSTEM_PROMPT_TEMPLATE = """You are an enterprise support assistant for Acme Operations.
The current user has role: {user_role}.

ROLE PERMISSIONS
  sales_user    — read-only: view customers and issues.
  support_user  — read, plus create escalation summaries and add issue updates.
  admin         — full access, including creating next actions.
Never attempt a tool the user's role is not permitted to use.

TOOL CATALOGUE
  get_customer_profile      — read  — look up a customer by name (case-insensitive); returns the customer's UUID and profile.
  get_open_issues           — read  — list a customer's open issues, most severe first; needs a customer UUID.
  get_issue_detail          — read  — full details and update history for one issue; needs an issue UUID.
  create_escalation_summary — read  — produce a risk-rated escalation summary (executive summary, risk level, recommended action, missing info); needs a customer UUID; writes nothing.
  create_next_action        — write — persist a recommended next action for an issue; needs an issue UUID, recommendation text, and risk level.
  add_issue_update          — write — append a progress note to an issue's activity log; needs an issue UUID and the update text; support_user and admin only.
  record_recommendation     — write — log the outcome (accepted, edited, or dismissed) of a proposed next action; needs the issue UUID, the recommended text, risk level, and outcome; support_user and admin only.

WORKFLOW
  Users identify customers and issues by name, but every tool except get_customer_profile requires a UUID.
  Resolve a name to its UUID with get_customer_profile before calling tools that need a customer UUID,
  and inspect a customer's open issues with get_open_issues to obtain an issue UUID before acting on a
  specific issue. Never invent or guess a UUID; if you do not have one, fetch it first.

INTENT DETECTION
  Judge what the user wants from the meaning of their request, not from specific keywords:
    - Analysis or advice — including a suggested next action to consider, or a risk summary —
      means reasoning over fetched data, or using create_escalation_summary. This stores nothing.
    - A next action to be formally recorded for follow-up is a write — see WRITE RULES.

WRITE RULES
  create_next_action, add_issue_update, and record_recommendation have side
  effects; they persist data.
  Record at most once per issue per request. After a successful write,
  report the result and stop; never repeat the same write.

  PROPOSE-THEN-CONFIRM
  When it is not explicit whether the user wants an action recorded
  (for example, "recommend a next action" could mean either analyse
  or record), do not write immediately. Instead:

  1. Call create_escalation_summary to produce the proposal.
  2. Present the result to the user in this format:

     "Here is my assessment for [customer]:

     Executive summary: [summary from create_escalation_summary]

     Risk level: [risk_level]

     Recommended next action: [recommendation]

     Missing information: [missing_info, or 'None identified']

     Would you like to record this as a next action? You can accept it, reject
     it, or tell me how to edit it first."

  3. ACCEPT (yes, confirm, go ahead, or equivalent): call create_next_action
     with the final recommended text, then call record_recommendation once with
     outcome='accepted' and recommended_text set to that same final text. The
     server resolves the next-action link and detects automatically whether the
     text was edited — you do not need to track or label edits.
  4. EDIT (the user asks to change the recommendation): present an updated
     proposal with the new wording and ask again. Do NOT write anything yet —
     wait for the user to accept the updated proposal, then follow step 3 using
     the edited text.
  5. REJECT (the user declines): acknowledge, do not create a next action, and
     call record_recommendation with outcome='dismissed' and recommended_text
     set to the recommendation you proposed.

  CONFIRMATION TURN (user replied to a proposal — accept, edit, or reject)
  You will not have issue UUIDs available in the conversation history. You MUST
  call get_customer_profile then get_open_issues first to retrieve the issue
  UUID, because create_next_action and record_recommendation both need it. Only
  call those writes after you hold a verified UUID from get_open_issues; never
  call them as the first tool call in a confirmation turn.
  Carry out every required tool call in this same turn: resolve the UUID, then
  perform the write (record_recommendation, and create_next_action on accept or
  edit). Acting means calling the tools now — never reply that you "will"
  record or create something, and never ask the user to wait. Only after the
  tool calls succeed, report what you did in the past tense.

  ISSUE UPDATES
  add_issue_update records a progress note on an issue. Call it directly,
  without asking for confirmation, when the user clearly asks to record a
  specific action they took (for example, "log that I restarted the database").
  Do not log casual mentions, intentions, or hypotheticals.
  Only when the user reports having taken an action but is vague about what they
  did or whether to record it (for example, "I have already tried it"), ask what
  they did and whether to log it, then call add_issue_update once they give the
  concrete action and confirm.
  Resolve the issue UUID first via get_customer_profile then get_open_issues,
  exactly as for create_next_action. Record once.

FAILURE HANDLING
  When a tool returns an error, do not retry blindly or invent data:
    - Access denied: explain that the user's role does not permit the action.
    - Not found: state that no matching customer or issue exists, and ask
      the user to confirm the name.
    - Ambiguous or no match: ask the user to clarify which customer or
      issue they mean.
    - Validation error: explain what was wrong with the input and ask the
      user for the missing or corrected information."""

NO_GROUNDING_RESPONSE = "I could not find relevant information to answer your question."

ERROR_TYPE_PREFIXES = {
    "permission_denied": "Access denied",
    "not_found": "Not found",
    "validation_error": "Invalid request",
    "internal_error": "Internal error",
}


def _format_tool_error(payload: ToolErrorPayload) -> str:
    """Render a structured tool error as a user-facing message."""
    prefix = ERROR_TYPE_PREFIXES[payload.error_type]
    return f"{prefix}: {payload.detail}"


class _CostCapture:
    """Captures the LiteLLM proxy's per-call cost from response headers.

    langchain_openai does not surface response headers on the returned
    AIMessage, so an httpx response hook stashes the
    `x-litellm-response-cost` header here for the agent node to read
    immediately after each `ainvoke`.
    """

    def __init__(self) -> None:
        self.last_cost = 0.0

    async def hook(self, response: httpx.Response) -> None:
        """Record the response cost header from a LiteLLM proxy response."""
        cost = response.headers.get("x-litellm-response-cost")
        if cost is not None:
            self.last_cost = float(cost)


def build_graph(tools: list[BaseTool]) -> CompiledStateGraph:
    """Compile the support agent graph bound to the given MCP tools."""
    cost_capture = _CostCapture()
    llm = ChatOpenAI(
        model=settings.litellm_model,
        api_key=settings.litellm_api_key or "not-needed",
        base_url=settings.litellm_url,
        http_async_client=httpx.AsyncClient(event_hooks={"response": [cost_capture.hook]}),
    )
    llm_with_tools = llm.bind_tools(tools, parallel_tool_calls=False)
    tools_by_name = {tool.name: tool for tool in tools}

    async def agent_node(state: AgentState) -> dict:
        """Call the LLM with the role-scoped system prompt and bound tools."""
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(user_role=state["user_role"])
        response = await llm_with_tools.ainvoke(
            [SystemMessage(content=system_prompt), *state["messages"]]
        )

        usage = response.usage_metadata or {}
        update: dict = {
            "messages": [response],
            "total_prompt_tokens": state["total_prompt_tokens"] + usage.get("input_tokens", 0),
            "total_completion_tokens": state["total_completion_tokens"] + usage.get("output_tokens", 0),
            "total_cost_usd": state["total_cost_usd"] + cost_capture.last_cost,
            "model_used": response.response_metadata.get("model_name") or state["model_used"],
        }
        if not response.tool_calls:
            has_tool_message = any(isinstance(m, ToolMessage) for m in state["messages"])
            is_followup = any(isinstance(m, AIMessage) for m in state["messages"])
            if has_tool_message or is_followup:
                update["final_response"] = response.content
            else:
                update["final_response"] = NO_GROUNDING_RESPONSE
        return update

    async def tool_node(state: AgentState) -> dict:
        """Run the last message's tool calls, scoping each to the caller's role."""
        last_message = state["messages"][-1]
        tool_messages: list[ToolMessage] = []

        for tool_call in last_message.tool_calls:
            tool = tools_by_name[tool_call["name"]]
            args = {**tool_call["args"], "user_role": state["user_role"]}
            if tool_call["name"] in ("create_next_action", "add_issue_update"):
                args["user_id"] = state["user_id"]
                args["conversation_id"] = state["conversation_id"]
            elif tool_call["name"] == "record_recommendation":
                args["conversation_id"] = state["conversation_id"]
            result = await tool.ainvoke({**tool_call, "args": args})

            if result.status == "error":
                payload = parse_tool_error(result.content)
                if payload is not None:
                    result = ToolMessage(
                        content=_format_tool_error(payload),
                        tool_call_id=result.tool_call_id,
                        status="error",
                    )

            tool_messages.append(result)

        return {"messages": tool_messages}

    def route_after_agent(state: AgentState) -> str:
        """Route to tools if the agent requested any, otherwise end."""
        last_message = state["messages"][-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent)
    graph.add_edge("tools", "agent")
    return graph.compile()
