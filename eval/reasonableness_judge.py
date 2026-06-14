"""LLM-as-judge for recommendation reasonableness (eval Phase 2).

Standalone CLI helper (isolated eval venv), imported by eval/run_eval.py only
when RAGAS_ENABLED is set. Uses a cross-family judge (EVAL_JUDGE_MODEL, default
claude-sonnet-4) via the LiteLLM gateway to score the agent's recommended next
action against the issue facts it retrieved.

The recommendation source differs by case:
  - a recorded next action (e.g. Q5) -> next_actions.recommendation_text
  - a propose-then-confirm proposal (e.g. Q9) writes no row, so the
    recommendation comes from the create_escalation_summary tool output.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from ragas_scorer import _extract_text

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

POSTGRES_URL = os.environ.get("POSTGRES_URL", "postgresql://postgres:postgres@localhost:5432/acme")
LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY", "")
EVAL_JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "gpt-4o")

REASONABLENESS_THRESHOLD = 3

RUBRIC = """You are evaluating a support agent's recommended next action for an enterprise customer issue.

Customer and issue information the agent retrieved:
{context}

Agent's recommended next action:
{recommendation}
Agent's stated risk level: {risk_level}

Score the recommendation from 1 to 5:
  5 = directly addresses the issue, clearly actionable, severity-appropriate, grounded in the facts above
  3 = partially addresses the issue, somewhat actionable
  1 = vague, inappropriate severity, or not grounded in the facts

Return ONLY a JSON object with exactly these keys:
  "score": integer 1-5,
  "rationale": string,
  "addresses_issue": boolean,
  "is_actionable": boolean,
  "severity_appropriate": boolean,
  "grounded_in_facts": boolean"""


class ReasonablenessScore(BaseModel):
    """Structured judgement of a recommended next action."""

    score: int
    rationale: str
    addresses_issue: bool
    is_actionable: bool
    severity_appropriate: bool
    grounded_in_facts: bool


def fetch_recommendation(conversation_id: str) -> tuple[str, str] | None:
    """Return (recommendation_text, risk_level) for a conversation, or None.

    Prefers a recorded next action; falls back to the latest escalation-summary
    proposal (propose-then-confirm cases write no next action).
    """
    if not conversation_id:
        return None
    conn = psycopg2.connect(POSTGRES_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT recommendation_text, risk_level FROM next_actions "
                "WHERE conversation_id = %s ORDER BY created_at DESC LIMIT 1",
                (conversation_id,),
            )
            row = cur.fetchone()
            if row:
                return (row[0], row[1])
            cur.execute(
                "SELECT tool_output FROM agent_actions "
                "WHERE conversation_id = %s AND tool_name = 'create_escalation_summary' "
                "ORDER BY created_at DESC LIMIT 1",
                (conversation_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row or row[0] is None:
        return None
    try:
        summary = json.loads(_extract_text(row[0]))
        return (summary.get("recommendation", ""), summary.get("risk_level", ""))
    except (json.JSONDecodeError, AttributeError):
        return None


def judge(context: str, recommendation: str, risk_level: str) -> ReasonablenessScore | None:
    """Score a recommendation against the issue context, or None if the judge output is unparseable."""
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=EVAL_JUDGE_MODEL,
        api_key=LITELLM_API_KEY or "not-needed",
        base_url=LITELLM_URL,
        temperature=0,
    )
    prompt = RUBRIC.format(context=context, recommendation=recommendation, risk_level=risk_level)
    content = llm.invoke(prompt).content
    text = content if isinstance(content, str) else str(content)
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return ReasonablenessScore.model_validate_json(text)
    except ValidationError:
        try:
            return ReasonablenessScore.model_validate_json(text[text.index("{"): text.rindex("}") + 1])
        except (ValueError, ValidationError):
            return None
