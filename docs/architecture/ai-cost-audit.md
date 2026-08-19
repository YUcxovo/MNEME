# AI Cost Audit (Milestone 4)

Owner: Yifan Zhang. Audited at revision `1a604b3` (2026-07-24) by static
inspection of call sites, configuration defaults, and the pricing table in
`mneme/ai/pricing.py` (list prices reviewed 2026-07). All dollar figures are
**estimates** from list prices and token approximations, not measured spend;
measured numbers come from the persisted `estimated_cost` telemetry once the
deployed pipeline has run.

## Call-site inventory

| Call site | Trigger | Model (default) | Cache | Budget check |
|---|---|---|---|---|
| Summarization worker | ARQ job per paper version | `llm_summary_model` = claude-opus-4-8 | 7d TTL + identity row in `paper_summaries` | yes |
| Grounded QA | `/qa/ask` per request | `llm_qa_model` = claude-opus-4-8 | 24h TTL keyed on question + evidence + model + prompt version | yes |
| Query embedding | `/qa/ask`, eval CLI | text-embedding-3-small | none (single short string) | yes |
| Chunk embeddings | ARQ embed job per paper version | text-embedding-3-small, batch 64 | idempotent via `content_hash` | yes |
| Recommendation scoring | digest jobs | none (cosine over stored vectors) | n/a | n/a |

The summarization worker and `/qa/ask` persist `estimated_cost`, token
counts, and latency on their `paper_summaries` / `qa_messages` rows, so
their live spend is auditable from the database. Eval-CLI completions are
**not** persisted (they share the cache only); their spend is recorded in
the run's JSON report and in the shared daily budget counter.

## Unit economics (estimated)

Assumptions: summary input capped at 60k chars (~15k tokens), summary output
capped at 1024 tokens; QA context ~6 chunks x 450 tokens plus prompt (~3k
input tokens), QA output capped at 512 tokens.

| Operation | opus-4-8 | haiku-4-5 | deepseek-v4-flash |
|---|---|---|---|
| One paper summary | ~$0.100 | ~$0.020 | ~$0.0024 |
| One QA answer | ~$0.028 | ~$0.006 | ~$0.0006 |
| One paper embedded | ~$0.0003 | same | same |

Against the default `ai_daily_budget_usd = 5`:

- On opus-4-8, ~50 summaries or ~180 QA calls exhaust the day. A single
  daily ingestion batch can consume the entire cap.
- On haiku-4-5, ~250 summaries/day fit; QA becomes negligible.
- A full 15-fixture eval run (12 answered) costs ~$0.34 on opus vs ~$0.07
  on haiku.

## Findings

1. **F1 -- default routing sends bulk summarization to the most expensive
   model.** Both `llm_summary_model` and `llm_qa_model` default to
   claude-opus-4-8. Summarization is bulk background work whose output is
   schema-constrained JSON; it is the workload least likely to need the
   flagship tier and the one that dominates spend (~5x QA per unit).
   **Recommendation:** route `SUMMARIZE` to claude-haiku-4-5 (or
   deepseek-v4-flash) by default and keep the flagship tier for QA, where
   grounding quality is user-visible. Decision owner: Yifan; requires an
   eval comparison on the summary seed before switching (structured-output
   fidelity, not just cost).
2. **F2 -- BudgetGuard thresholds are coherent but the cap is one shared
   pool.** Summaries, QA, and embeddings draw from the same daily $5. A
   large ingestion day can starve interactive QA. Acceptable for the demo
   deployment; if it bites, split caps per task rather than raising the
   global one. The documented check-then-spend race (overshoot bounded by
   in-flight completions) is acceptable for a daily cap.
3. **F3 -- embedding batch size 64 is fine.** Provider limits allow more,
   but larger batches raise timeout risk for marginal savings; chunk
   embedding cost is three orders of magnitude below LLM cost. No change.
4. **F4 -- caching posture is sound.** Prompt-version participates in every
   cache key, so template changes invalidate cleanly; summary identity rows
   make reruns free; unknown models price at the most expensive tier, so
   budget accounting never undercounts.

## Status

F1 is a recommendation pending an owner decision and a summary-quality
comparison; no default was changed in this audit. F2-F4 require no action.
