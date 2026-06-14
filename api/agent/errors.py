"""Parsing of structured tool-call error payloads from MCP."""

from __future__ import annotations

from pydantic import ValidationError

from models.agent import ToolErrorPayload


def _flatten_content(content: str | list) -> str:
    """Flatten a ToolMessage's content (string or content blocks) into one string."""
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block["text"])
        else:
            parts.append(str(block))
    return "\n".join(parts)


def parse_tool_error(content: str | list) -> ToolErrorPayload | None:
    """Parse a ToolMessage's error content as a ToolErrorPayload, or return None.

    FastMCP wraps a raised exception's message as
    "Error executing tool {name}: {message}", so the JSON payload is a
    suffix of the text rather than the whole string.
    """
    text = _flatten_content(content)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None

    try:
        return ToolErrorPayload.model_validate_json(text[start : end + 1])
    except ValidationError:
        return None
