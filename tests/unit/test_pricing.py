"""Unit checks for token-based LLM cost estimation.

Pure function under test (no stack required). Run with:
    python tests/test_pricing.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "api"))

from agent.pricing import MODEL_PRICING, compute_cost_usd  # noqa: E402


def check(name: str, fn: Callable[[], None]) -> None:
    """Run fn and print PASS/FAIL for the named check."""
    try:
        fn()
        print(f"PASS: {name}")
    except Exception as exc:
        print(f"FAIL: {name} -> {exc}")


def test_uncached_cost() -> None:
    """Cost with no cache hits is fresh input plus output at full rates."""
    cost = compute_cost_usd("gpt-4o-mini", input_tokens=1000, output_tokens=500)
    expected = (1000 * 0.15 + 500 * 0.60) / 1_000_000
    assert abs(cost - expected) < 1e-12, f"{cost} != {expected}"


def test_cached_tokens_discounted() -> None:
    """Cached input tokens bill at the discounted rate, not the full rate."""
    cost = compute_cost_usd(
        "gpt-4o-mini", input_tokens=2775, output_tokens=10, cached_input_tokens=2688
    )
    expected = (87 * 0.15 + 2688 * 0.075 + 10 * 0.60) / 1_000_000
    assert abs(cost - expected) < 1e-12, f"{cost} != {expected}"


def test_caching_is_cheaper_than_naive() -> None:
    """Accounting for the cache yields a strictly lower cost than ignoring it."""
    cache_aware = compute_cost_usd(
        "gpt-4o-mini", input_tokens=2775, output_tokens=10, cached_input_tokens=2688
    )
    naive = compute_cost_usd("gpt-4o-mini", input_tokens=2775, output_tokens=10)
    assert cache_aware < naive, f"{cache_aware} not < {naive}"


def test_cached_not_exceeding_input() -> None:
    """cached_input_tokens never produces negative fresh-input billing."""
    cost = compute_cost_usd(
        "gpt-4o-mini", input_tokens=100, output_tokens=0, cached_input_tokens=500
    )
    expected = (500 * 0.075) / 1_000_000
    assert abs(cost - expected) < 1e-12, f"{cost} != {expected}"


def test_unpriced_model_returns_zero() -> None:
    """An unknown model returns 0.0 rather than raising."""
    assert "no-such-model" not in MODEL_PRICING
    assert compute_cost_usd("no-such-model", input_tokens=1000, output_tokens=1000) == 0.0


def run() -> None:
    """Run all checks, printing PASS/FAIL for each."""
    check("uncached cost", test_uncached_cost)
    check("cached tokens discounted", test_cached_tokens_discounted)
    check("cache-aware cheaper than naive", test_caching_is_cheaper_than_naive)
    check("cached tokens capped at input", test_cached_not_exceeding_input)
    check("unpriced model returns zero", test_unpriced_model_returns_zero)


if __name__ == "__main__":
    run()
