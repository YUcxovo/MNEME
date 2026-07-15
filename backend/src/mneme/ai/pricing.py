"""Static per-model pricing used for cost estimation and budget accounting."""

from decimal import Decimal

import structlog
from pydantic import BaseModel, ConfigDict

from mneme.ai.types import TokenUsage

logger = structlog.get_logger(__name__)

_MILLION = Decimal(1_000_000)


class ModelPricing(BaseModel):
    """USD price per million input/output tokens."""

    model_config = ConfigDict(frozen=True)

    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal


# Published list prices (USD per million tokens), reviewed 2026-07.
MODEL_PRICING: dict[str, ModelPricing] = {
    "claude-opus-4-8": ModelPricing(
        input_usd_per_mtok=Decimal("5.00"), output_usd_per_mtok=Decimal("25.00")
    ),
    "claude-sonnet-5": ModelPricing(
        input_usd_per_mtok=Decimal("3.00"), output_usd_per_mtok=Decimal("15.00")
    ),
    "claude-sonnet-4-6": ModelPricing(
        input_usd_per_mtok=Decimal("3.00"), output_usd_per_mtok=Decimal("15.00")
    ),
    "claude-haiku-4-5": ModelPricing(
        input_usd_per_mtok=Decimal("1.00"), output_usd_per_mtok=Decimal("5.00")
    ),
    "gpt-4o": ModelPricing(
        input_usd_per_mtok=Decimal("2.50"), output_usd_per_mtok=Decimal("10.00")
    ),
    "gpt-4o-mini": ModelPricing(
        input_usd_per_mtok=Decimal("0.15"), output_usd_per_mtok=Decimal("0.60")
    ),
    "gpt-4.1": ModelPricing(
        input_usd_per_mtok=Decimal("2.00"), output_usd_per_mtok=Decimal("8.00")
    ),
    "gpt-4.1-mini": ModelPricing(
        input_usd_per_mtok=Decimal("0.40"), output_usd_per_mtok=Decimal("1.60")
    ),
}

# Budget accounting must never undercount an unknown model, so the fallback is
# priced at the most expensive routable tier.
_FALLBACK_PRICING = ModelPricing(
    input_usd_per_mtok=Decimal("5.00"), output_usd_per_mtok=Decimal("25.00")
)


def estimate_cost(model: str, usage: TokenUsage) -> Decimal:
    """Return the estimated USD cost of one completion."""
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        logger.warning("unknown_model_pricing", model=model)
        pricing = _FALLBACK_PRICING
    return (
        Decimal(usage.input_tokens) * pricing.input_usd_per_mtok
        + Decimal(usage.output_tokens) * pricing.output_usd_per_mtok
    ) / _MILLION
