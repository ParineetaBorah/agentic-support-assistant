"""Token-based cost estimation for LLM calls.

Cost is estimated from token usage rather than read from the LiteLLM proxy's
x-litellm-response-cost header, because that header is unavailable on streaming
responses (cost is not known until the stream ends, after the headers are sent).

Prices are USD per 1M tokens from OpenAI's published pricing
(https://openai.com/api/pricing/), last verified 2026-06-16. Update both the
rates and that date when prices change.
"""

from __future__ import annotations

import structlog

from models.agent import ModelPricing

logger = structlog.get_logger()

MODEL_PRICING: dict[str, ModelPricing] = {
    "gpt-4o-mini": ModelPricing(input_per_1m=0.15, cached_input_per_1m=0.075, output_per_1m=0.60),
    "gpt-4o": ModelPricing(input_per_1m=2.50, cached_input_per_1m=1.25, output_per_1m=10.00),
}

_TOKENS_PER_MILLION = 1_000_000


def compute_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
) -> float:
    """Estimate the USD cost of one LLM call from its token usage.

    cached_input_tokens is the cache_read subset of input_tokens and is billed
    at the model's discounted cache rate. Returns 0.0 for a model absent from
    MODEL_PRICING, after logging a warning so the gap is visible.
    """
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        logger.warning("unpriced_model", model=model)
        return 0.0

    fresh_input_tokens = max(input_tokens - cached_input_tokens, 0)
    total = (
        fresh_input_tokens * pricing.input_per_1m
        + cached_input_tokens * pricing.cached_input_per_1m
        + output_tokens * pricing.output_per_1m
    )
    return total / _TOKENS_PER_MILLION
