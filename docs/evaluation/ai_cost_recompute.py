"""Recompute the thesis AI cost estimates from the retained price snapshot.

Reproduces every dollar figure in the Chapter 4 "AI Cost and Latency Audit"
section and in docs/architecture/ai-cost-audit.md from the list prices
retained in ai-cost-price-snapshot-2026-07-26.md plus the deployed caps.
Stdlib only: python3 docs/evaluation/ai_cost_recompute.py
"""

from decimal import Decimal

# USD per million tokens (input, output), from the snapshot reviewed 2026-07-26.
PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "claude-opus-4-8": (Decimal("5.00"), Decimal("25.00")),
    "claude-haiku-4-5": (Decimal("1.00"), Decimal("5.00")),
    "deepseek-v4-flash": (Decimal("0.14"), Decimal("0.28")),
    "text-embedding-3-small": (Decimal("0.02"), Decimal("0")),
}

MTOK = Decimal(1_000_000)

# Deployed caps and token approximations (~4 chars/token), see snapshot doc.
SUMMARY_INPUT_TOKENS = 15_000  # 60,000-char cap
SUMMARY_OUTPUT_TOKENS = 1_024
QA_INPUT_TOKENS = 3_000  # ~6 chunks x 450 tokens + prompt
QA_OUTPUT_TOKENS = 512
EMBED_TOKENS_PER_PAPER = 15_000
DAILY_BUDGET_USD = Decimal("5.00")
EVAL_ANSWERABLE_CASES = 12  # qa-seed-v2: 15 fixtures, 12 answerable


def completion_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    input_price, output_price = PRICES[model]
    return (Decimal(input_tokens) * input_price + Decimal(output_tokens) * output_price) / MTOK


def main() -> None:
    rows = []
    for model in ("claude-opus-4-8", "claude-haiku-4-5", "deepseek-v4-flash"):
        summary = completion_cost(model, SUMMARY_INPUT_TOKENS, SUMMARY_OUTPUT_TOKENS)
        qa = completion_cost(model, QA_INPUT_TOKENS, QA_OUTPUT_TOKENS)
        rows.append((model, summary, qa))
        print(f"{model:20s} summary ${summary:.4f}  qa ${qa:.4f}")

    embed = completion_cost("text-embedding-3-small", EMBED_TOKENS_PER_PAPER, 0)
    print(f"{'embed one paper':20s} ${embed:.5f}")

    opus_summary, opus_qa = rows[0][1], rows[0][2]
    haiku_summary = rows[1][1]
    print(f"opus summaries per $5 day: {int(DAILY_BUDGET_USD / opus_summary)}")
    print(f"opus qa calls per $5 day:  {int(DAILY_BUDGET_USD / opus_qa)}")
    print(f"haiku summaries per $5 day: {int(DAILY_BUDGET_USD / haiku_summary)}")
    opus_eval = opus_qa * EVAL_ANSWERABLE_CASES
    haiku_eval = rows[1][2] * EVAL_ANSWERABLE_CASES
    print(f"15-case eval run: opus ${opus_eval:.2f}  haiku ${haiku_eval:.2f}")

    # The figures cited in Chapter 4 and the cost audit, to one significant
    # rounding step; a failing assertion means the snapshot or caps changed
    # and the prose must be re-derived, not patched.
    assert round(opus_summary, 3) == Decimal("0.101")
    assert round(opus_qa, 3) == Decimal("0.028")
    assert round(haiku_summary, 3) == Decimal("0.020")
    assert round(rows[1][2], 3) == Decimal("0.006")
    assert round(rows[2][1], 4) == Decimal("0.0024")
    assert round(embed, 4) == Decimal("0.0003")
    assert int(DAILY_BUDGET_USD / opus_summary) == 49
    assert int(DAILY_BUDGET_USD / opus_qa) == 179
    assert int(DAILY_BUDGET_USD / haiku_summary) == 248
    assert round(opus_eval, 2) == Decimal("0.33")
    assert round(haiku_eval, 2) == Decimal("0.07")
    print("all thesis figures reproduced")


if __name__ == "__main__":
    main()
