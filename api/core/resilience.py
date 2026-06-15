"""Shared timeout and retry policy for outbound calls (LLM, MCP, Keycloak).

Centralised so the resilience knobs are visible and tunable in one place rather
than relying on library defaults.
"""

from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

# Outbound timeouts (seconds).
HTTP_TIMEOUT = 10.0  # Keycloak token / JWKS fetches
LLM_TIMEOUT = 60.0  # agent LLM calls via the LiteLLM gateway (can be slow)
MCP_TIMEOUT = 30.0  # MCP streamable-HTTP connection

# The OpenAI SDK applies exponential backoff between these retries.
LLM_MAX_RETRIES = 2

# Retry transient network failures (connection errors, timeouts) with exponential
# backoff. httpx.TimeoutException is a subclass of TransportError, so both are
# covered. Deliberately NOT retrying on HTTP 4xx/5xx — those come back as
# responses for the caller to handle (e.g. a 401 on bad credentials), and
# retrying them would be wrong or wasteful.
transient_http_retry = retry(
    retry=retry_if_exception_type(httpx.TransportError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4.0),
    reraise=True,
)
