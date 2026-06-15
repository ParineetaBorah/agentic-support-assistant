"""RAGAS faithfulness scoring for the eval harness (Phase 1: grounding only).

Standalone — imported by eval/run_eval.py only when RAGAS_ENABLED is set, so
ragas/datasets are not required for a plain eval run. Contexts are the agent's
tool outputs, read from agent_actions by conversation_id; faithfulness measures
whether the agent's answer is supported by those outputs (i.e. grounded).

The LiteLLM gateway is used as the judge LLM. Run from the eval/ virtualenv:
    eval/.venv/bin/python eval/run_eval.py   (with RAGAS_ENABLED=true)
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

POSTGRES_URL = os.environ.get("POSTGRES_URL", "postgresql://postgres:postgres@localhost:5432/acme")
LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY", "")
EVAL_JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "gpt-4o")

FAITHFULNESS_THRESHOLD = 0.7


def _extract_text(tool_output: object) -> str:
    """Flatten a stored agent_actions.tool_output (MCP content blocks) to plain text.

    psycopg2 usually decodes JSONB to Python objects, but values may also arrive
    as raw JSON strings, plain text, or empty — handle all of them defensively.
    """
    if isinstance(tool_output, str):
        stripped = tool_output.strip()
        if not stripped:
            return ""
        try:
            tool_output = json.loads(stripped)
        except json.JSONDecodeError:
            return tool_output
    if isinstance(tool_output, list):
        parts = [b.get("text", "") for b in tool_output if isinstance(b, dict) and b.get("text")]
        return "\n".join(part for part in parts if part)
    if isinstance(tool_output, dict):
        return tool_output.get("text") or json.dumps(tool_output)
    return str(tool_output)


def fetch_contexts(conversation_id: str) -> list[str]:
    """Return the agent's tool outputs for a conversation, oldest first, as plain-text contexts."""
    if not conversation_id:
        return []
    conn = psycopg2.connect(POSTGRES_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tool_output FROM agent_actions WHERE conversation_id = %s ORDER BY created_at",
                (conversation_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    contexts = [_extract_text(row[0]) for row in rows if row[0] is not None]
    return [text for text in contexts if text.strip()]


def score_faithfulness(question: str, answer: str, contexts: list[str]) -> float | None:
    """Return the RAGAS faithfulness score (0.0-1.0) of answer against contexts, or None if no contexts."""
    if not contexts:
        return None

    from datasets import Dataset
    from langchain_openai import ChatOpenAI
    from ragas import evaluate
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import faithfulness

    judge = LangchainLLMWrapper(
        ChatOpenAI(
            model=EVAL_JUDGE_MODEL,
            api_key=LITELLM_API_KEY or "not-needed",
            base_url=LITELLM_URL,
            temperature=0,
        )
    )
    dataset = Dataset.from_dict(
        {"question": [question], "answer": [answer], "contexts": [contexts]}
    )
    result = evaluate(dataset, metrics=[faithfulness], llm=judge, raise_exceptions=False)
    score = result["faithfulness"]
    if isinstance(score, list):
        score = score[0]
    # RAGAS returns NaN when a judge sub-call fails (raise_exceptions=False);
    # treat that as "could not score", not a grounding failure.
    if score is None or (isinstance(score, float) and math.isnan(score)):
        return None
    return float(score)


def grounding_score(conversation_id: str, question: str, answer: str) -> float | None:
    """Fetch the conversation's tool-output contexts and return the faithfulness score, or None."""
    contexts = fetch_contexts(conversation_id)
    return score_faithfulness(question, answer, contexts)
