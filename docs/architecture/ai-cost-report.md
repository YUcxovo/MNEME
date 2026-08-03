# AI Cost Report (Milestone 5)

Owner: Yifan Zhang. Final cost accounting for the development phase and a
projected monthly cost for one real user under the frozen Milestone 5
routing (`summarize` -> `claude-haiku-4-5`, `qa` -> `claude-opus-4-8`; see
`ai-prompt-freeze.md`). Companion to the Milestone 4 `ai-cost-audit.md`,
which estimated unit economics from list prices; this report uses measured
numbers where they exist and states plainly where they do not.

## Measured development spend

Milestones 1-3 developed and tested the AI layer against deterministic
provider fakes, at zero provider spend. Live LLM spend during development
is concentrated in the recorded Milestone 4 evaluation runs (caching
disabled or cold for every run, so each figure is genuine provider spend).
The raw run reports behind every figure in this table are retained on the
repository `docs` branch as
`docs/evaluation/qa/qa-seed-v2-run-2026-07-28-{opus,haiku}.json` and
`docs/evaluation/summaries/summary-tier-study-2026-07-28.json`:

| Recorded run (2026-07-28) | Model | Calls | Measured cost |
|---------------------------|-------|-------|---------------|
| Graded QA run, flagship | claude-opus-4-8 | 15 | $0.326 |
| Graded QA run, mid tier | claude-haiku-4-5 | 15 | $0.054 |
| Summary tier study, flagship | claude-opus-4-8 | 7 | $0.921 |
| Summary tier study, mid tier | claude-haiku-4-5 | 7 | $0.140 |
| **Total recorded** | | | **$1.441** |

Two smaller sources sit outside the recorded runs and were not measured:
the live end-to-end UI traces (one five-paper briefing preparation plus
single Q&A turns, repeated a handful of times) and ad-hoc manual calls
during integration. No per-call cost records or provider billing exports
were retained for them, so their cost is reported as unrecorded rather
than estimated, and this report claims no cumulative total beyond the
$1.441 measured above. The shared `BudgetGuard` cap
(`ai_daily_budget_usd = 5`) bounds any single development day but not
multi-day cumulative spend. Corpus embeddings used the local fastembed
backend at $0.

The eval CLI intentionally does not persist to `qa_messages` (its JSON
report is the durable record), and the local demo database confirms zero
persisted product-path spend rows; the table above is therefore the
complete measured record, not a sample.

## Measured unit costs

Derived from the recorded runs (per-call averages, cold cache):

| Operation | Frozen route | Measured unit cost |
|-----------|--------------|--------------------|
| One paper summary | claude-haiku-4-5 | ~$0.020 |
| One grounded QA answer | claude-opus-4-8 | ~$0.022 |
| One paper embedded | fastembed local / text-embedding-3-small | $0 / ~$0.0003 |

These land close to the Milestone 4 list-price estimates ($0.020 haiku
summary, $0.028 opus QA), which cross-validates the pricing table and the
token-cap assumptions.

## Projected monthly cost, one real user

Assumed profile: the weekly Research Briefing prepares 5 new papers
(summary + chunking + embedding), and the user asks 40 grounded questions
per month (~2 per weekday). Cold-cache worst case:

| Component | Volume / month | Cost |
|-----------|----------------|------|
| Summaries (haiku route) | ~22 papers | $0.44 |
| QA answers (opus route) | 40 questions | $0.88 |
| Embeddings (OpenAI backend) | ~22 papers | $0.01 |
| **Total** | | **~$1.33 / user-month** |

Sensitivity:

- All-flagship routing (the pre-freeze default) would cost ~$3.7 for the
  same profile; the frozen split routing keeps quality where it is
  user-visible and cuts the bulk-work cost ~6.6x.
- The 24 h QA cache and 7 d summary cache make repeated questions and
  re-opened papers free, so real spend sits below the cold-cache figure.
- The DeepSeek route (~$0.0006/QA, ~$0.0024/summary from the audit's list
  prices) remains available per-environment for cost-constrained
  deployments, but has no recorded grounding evaluation and would need a
  graded run before serving users.

Against the default `ai_daily_budget_usd = 5`, one projected user consumes
under 1% of a month of budget headroom; the cap is sized for demo-day
safety (a runaway ingestion loop stops within one day at $5), not as a
scaling limit.

## Standing conclusions

1. Development discipline held: fakes for iteration, a handful of recorded
   live runs for evidence. Measured recorded spend is $1.44; the only
   spend outside that record (UI traces and ad-hoc integration calls) is
   unrecorded and is reported as such, not estimated away.
2. The frozen routing is the cost story: measured, not estimated, and the
   flagship tier is reserved for the one task whose failure contract
   (refusal markers) measurably needs it.
3. The next spend-relevant decision is bulk re-summarization of any new
   corpus: at ~$0.020/paper it is cheap, but it should run after prompt
   changes are frozen, not before, to avoid paying twice.
