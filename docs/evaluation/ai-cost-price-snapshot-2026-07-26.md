# AI Provider List-Price Snapshot (2026-07-26)

Owner: Yifan Zhang. This snapshot retains the official list prices behind
every dollar figure in the thesis section "AI Cost and Latency Audit"
(Chapter 4) and in `docs/architecture/ai-cost-audit.md` (audited at
`1a604b3`). Review date: **2026-07-26**, by fetching the official provider
pricing pages listed below. Prices are USD per million tokens, standard
(non-batch, cache-miss) rates.

Companion artifact: `docs/evaluation/ai_cost_recompute.py` recomputes every
thesis dollar figure from this table plus the deployed caps; run
`python3 docs/evaluation/ai_cost_recompute.py` (stdlib only).

## Verified price rows

| Model | Input $/Mtok | Output $/Mtok | Matches `mneme/ai/pricing.py` @ `1a604b3` | Official source |
|---|---|---|---|---|
| claude-opus-4-8 | 5.00 | 25.00 | yes | <https://platform.claude.com/docs/en/about-claude/pricing> |
| claude-haiku-4-5 | 1.00 | 5.00 | yes | <https://platform.claude.com/docs/en/about-claude/pricing> |
| claude-sonnet-4-6 | 3.00 | 15.00 | yes | <https://platform.claude.com/docs/en/about-claude/pricing> |
| claude-sonnet-5 | 2.00 (intro) / 3.00 (from 2026-09-01) | 10.00 (intro) / 15.00 | see note 1 | <https://platform.claude.com/docs/en/about-claude/pricing> |
| deepseek-v4-flash | 0.14 | 0.28 | yes | <https://api-docs.deepseek.com/quick_start/pricing> |
| deepseek-v4-pro | 0.435 | 0.87 | yes | <https://api-docs.deepseek.com/quick_start/pricing> |
| text-embedding-3-small | 0.02 | n/a | yes | <https://developers.openai.com/api/docs/models/text-embedding-3-small> |

Notes:

1. **claude-sonnet-5**: the official page lists introductory pricing of
   $2/$10 through 2026-08-31 and standard pricing of $3/$15 from
   2026-09-01. `pricing.py` records the standard $3/$15, which overestimates
   cost during the introductory window. Sonnet is not used in any thesis
   dollar figure, so no thesis number is affected.
2. **OpenAI gpt-4o / gpt-4.1 family**: these rows exist in `pricing.py` but
   no longer appear on OpenAI's current headline pricing page
   (<https://developers.openai.com/api/docs/pricing>), which lists only the
   gpt-5.x series as of the review date. They could therefore not be
   re-verified against an official page and are **not** used in any thesis
   dollar figure. If an OpenAI chat route is ever enabled, re-verify before
   citing costs.
3. `text-embedding-3-small` is absent from the headline pricing page but its
   official model page states $0.02 per 1M tokens; embedding cost is three
   orders of magnitude below LLM cost in all thesis figures, so this row is
   not sensitive.

## Deployed caps and token assumptions (inputs to the calculation)

Quoted from the audited configuration (`backend/src/mneme/core/config.py`
and the audit at `1a604b3`); token counts assume ~4 characters per token.

| Parameter | Value | Basis |
|---|---|---|
| Summary input cap | 60,000 chars, approximately 15,000 tokens | `config.py` summarization cap |
| Summary output cap | 1,024 tokens | `config.py` |
| Q&A context | ~6 chunks x 450 tokens + prompt, approximately 3,000 input tokens | retrieval `top_n=4` + up to 2 anchors, chunk size cap |
| Q&A output cap | 512 tokens | `config.py` |
| Paper embedding volume | approximately 15,000 tokens per paper | same text volume as summary input |
| Daily budget | $5.00 | `ai_daily_budget_usd` default |
| Evaluation set | 15 fixtures, 12 answerable | `qa-seed-v2` |

## Figures this snapshot supports

One paper summary ~$0.101 (opus-4-8) / ~$0.020 (haiku-4-5) /
~$0.0024 (deepseek-v4-flash); one grounded answer ~$0.028 / ~$0.006 /
~$0.0006; one paper embedded ~$0.0003; ~50 opus summaries or ~180 opus Q&A
calls exhaust the $5 daily cap (exact quotients 49, 179, and 248 for the
~250 haiku summaries); a full 15-case evaluation run ~$0.33 (opus) vs
~$0.07 (haiku). Every figure is rounded once from the script's exact
result, never recomputed from a rounded intermediate, so the evaluation-run
figure is $0.33 rather than 12 x the rounded $0.028. All derivations are in
the companion script and are estimates, not measured spend.
