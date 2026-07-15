"""Cost estimation against the static pricing table."""

from decimal import Decimal

import pytest

from mneme.ai.pricing import estimate_cost
from mneme.ai.types import TokenUsage


@pytest.mark.base
def test_known_model_uses_published_prices() -> None:
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=200_000)

    cost = estimate_cost("claude-haiku-4-5", usage)

    assert cost == Decimal("1.00") + Decimal("0.2") * Decimal("5.00")


@pytest.mark.base
def test_zero_usage_costs_nothing() -> None:
    assert estimate_cost("claude-opus-4-8", TokenUsage(input_tokens=0, output_tokens=0)) == 0


@pytest.mark.base
def test_unknown_model_falls_back_to_conservative_pricing() -> None:
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)

    cost = estimate_cost("mystery-model", usage)

    assert cost == Decimal("30.00")
