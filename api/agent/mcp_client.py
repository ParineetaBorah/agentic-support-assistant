"""MCP client for the support agent.

Connects to mcp_server over streamable HTTP and exposes its tools as
LangChain-compatible tools.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from core.config import settings
from core.resilience import MCP_TIMEOUT


@asynccontextmanager
async def get_mcp_tools() -> AsyncIterator[list[BaseTool]]:
    """Yield LangChain-compatible tools for all 5 Acme MCP tools.

    The underlying HTTP session stays open for the duration of the
    `async with` block, since each returned tool calls back into it.
    """
    async with streamablehttp_client(settings.mcp_server_url, timeout=MCP_TIMEOUT) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield await load_mcp_tools(session)
