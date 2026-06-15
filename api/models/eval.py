"""Pydantic models for the support agent eval harness."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class EvalTestCase(BaseModel):
    """A single eval test case run against POST /chat."""

    id: str
    question: str
    user: Literal["alice", "bob", "carol"]
    context_turns: list[str] = []
    expected_tool_sequence: list[str]
    expected_grounded: bool
    expected_outcome: Literal["success", "guardrail_blocked", "propose_then_confirm"]
    judge_reasonableness: bool = False


class EvalResult(BaseModel):
    """The outcome of running one EvalTestCase against /chat."""

    id: str
    question: str
    user: str
    conversation_id: str
    expected_tool_sequence: list[str]
    actual_tools_called: list[str]
    trajectory_pass: bool
    expected_grounded: bool
    grounded: bool
    expected_outcome: Literal["success", "guardrail_blocked", "propose_then_confirm"]
    judge_reasonableness: bool = False
    response_text: str
    duration_ms: float
    cost_usd: float
    total_tokens: int
    passed: bool
    reason: str


class EvalReport(BaseModel):
    """Summary of a full eval run across all test cases."""

    total: int
    passed: int
    failed: int
    results: list[EvalResult]
