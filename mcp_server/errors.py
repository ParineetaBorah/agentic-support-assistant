"""Structured JSON error payloads returned by MCP tools on failure.

FastMCP serializes a raised exception's message verbatim as the tool result's
error text, so encoding a ToolErrorPayload as JSON here lets api/agent/errors.py
parse it back into a typed payload instead of pattern-matching error text.
"""

from __future__ import annotations

from models import ToolErrorPayload


def permission_denied(role: str, tool: str) -> str:
    """Return a JSON ToolErrorPayload for a role not permitted to call a tool."""
    return ToolErrorPayload(
        error_type="permission_denied",
        detail=f"Role '{role}' is not permitted to call '{tool}'.",
    ).model_dump_json()


def not_found(resource: str, identifier: str) -> str:
    """Return a JSON ToolErrorPayload for a resource that could not be found."""
    return ToolErrorPayload(
        error_type="not_found",
        detail=f"{resource.capitalize()} '{identifier}' not found.",
    ).model_dump_json()


def validation_error(detail: str) -> str:
    """Return a JSON ToolErrorPayload for a validation failure."""
    return ToolErrorPayload(error_type="validation_error", detail=detail).model_dump_json()
