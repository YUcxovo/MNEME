# Chapter 4 AI/RAG evidence ledger

Non-rendered ledger for the AI, retrieval, provider-routing, latency, token,
and cost claims in `contents/chapter_4.tex`. Owner: Yifan Zhang. This ledger
closes `YIFAN-04`. It does not cover Android measurements (Hanyang), mobile
modules (Heng), or the behavior/graph backend mechanisms (Ruiyu).

Sign-off date: 2026-07-29. Every rendered value below was recomputed from the
retained artifact during this pass, not copied from an earlier draft.

## Retained artifacts

- `docs/evaluation/qa/qa-seed-v2-run-2026-07-28-opus.json`
  - SHA-256:
    `c64690beadfc7970892388a694f0e7053246692f5e1c46a2567e852e1dd60491`
  - Backend revision `e11e385`, measured 2026-07-28T00:30:00Z.
- `docs/evaluation/qa/qa-seed-v2-run-2026-07-28-haiku.json`
  - SHA-256:
    `4750653605be2b7fc65d3173e079dfbab035749e157d7b33ec1ef15e0f79c473`
  - Backend revision `2624df7`, measured 2026-07-28T01:15:00Z, cache disabled.
- `docs/evaluation/summaries/summary-tier-study-2026-07-28.json`
  - SHA-256:
    `e9bae4aa4d33a5272caeb5d13eb6eafd8f1933d80db0ee7f699b072a6c8ebd57`
  - Backend revision `2624df7`, measured 2026-07-28T01:02:00Z, cache disabled.
- `docs/evaluation/ai-cost-price-snapshot-2026-07-26.md`
  - SHA-256:
    `ff54e4aaea27b799cac8524659c9c839fe327b7c9b8947ff8c54f3e9f64f51df`
- `docs/evaluation/ai_cost_recompute.py`
  - SHA-256:
    `b65c7ed60ce78894106b4e9e2ce4a8cfd4eed3ec21bd3c1e7a7dd25bfde836be`

## Corpus and fixture identity

Fixture version `qa-seed-v2`: 15 cases, 12 answerable and 3 unanswerable, over
seven pinned arXiv papers (1706.03762, 1810.04805, 2005.11401, 2006.11239,
2010.11929, 2106.09685, 2305.18290). Both runs record `evaluated = 15` and an
empty `skipped` list, so no case was excluded after the fact. The same seven
papers form the summary tier study.

## Run configuration

Both QA runs share `retrieval_top_k = 8`, `context_anchor_count = 2`,
`rerank_top_n = 4`, `min_evidence_score = 0.25`, `max_output_tokens = 512`,
and `prompt_version = qa-v2`. Only `llm_model` and `cache_enabled` differ.

The flagship run has `cache_enabled = true` but its provenance note records a
cold cache and all 15 completions live; the Haiku run disabled the cache
outright. Chapter 4 therefore states that no completion in the reported run
carried a cached contribution, which holds for both.

Known artifact quirk: `run_config.embedding_model` echoes the configured
logical id `text-embedding-3-small`, while the provenance note records the
embeddings that actually ran, local `fastembed` with `BAAI/bge-small-en-v1.5`.
The 384-dimension figure in the thesis follows the provenance note and the
observed padding to the 1,536-dimension store; `text-embedding-3-small` is
1,536-dimension and is used only for the cost estimate of the embedding
operation. The chapter names the fastembed model explicitly so the two cannot
be confused.

## Table 4-14, flagship graded run

| Rendered value | Artifact field | Raw value |
|---|---|---|
| Evaluated fixtures 15 | `evaluated` | 15 |
| Citation rate 1.00 | `report.citation_rate` | 1.0 |
| Source-match rate 1.00 | `report.source_match_rate` | 1.0 |
| Partial-match rate 0.00 | `report.partial_match_rate` | 0.0 |
| Mean keyword coverage 0.94 | `report.mean_keyword_coverage` | 0.9444444444444445 |
| False-refusal rate 0.00 | `report.false_refusal_rate` | 0.0 |
| Refusal accuracy 2 of 3 | `report.refusal_accuracy` | 0.6666666666666666 |
| Section placement 4 of 12 | `report.recall_at_k` | 0.3333333333333333 |
| Mean generation latency 4,616 ms | `report.mean_generation_latency_ms` | 4616.0 |
| Mean pipeline latency 4,699 ms | `report.mean_pipeline_latency_ms` | 4698.533333333334 |
| Generation tokens 50,095 / 3,037 | `report.total_generation_{input,output}_tokens` | 50095 / 3037 |
| Measured run cost $0.326 | `report.total_generation_cost` | 0.326400 |

## Table 4-15, tier comparison

| Rendered value | Flagship raw | Mid raw |
|---|---|---|
| Citation rate 1.00 / 1.00 | 1.0 | 1.0 |
| Source-matched full/partial 12/0 and 11/1 | 1.0 / 0.0 | 0.9166666666666666 / 0.08333333333333333 |
| Mean keyword coverage 0.94 / 0.92 | 0.9444444444444445 | 0.9166666666666666 |
| False refusals 0 of 12 | 0.0 | 0.0 |
| Refusal-marker adherence 2 of 3 and 0 of 3 | 0.6666666666666666 | 0.0 |
| Section placement 4 of 12 both | 0.3333333333333333 | 0.3333333333333333 |
| Pipeline latency 4,699 / 3,422 ms | 4698.533333333334 | 3421.6 |
| Measured run cost $0.326 / $0.054 | 0.326400 | 0.053575 |

The identical section-placement value is expected: retrieval and reranking do
not involve the generation model, and both runs used identical retrieval
settings over identical fixtures.

## Table 4-16, summary tier study

Aggregated over the seven `papers` records of each tier.

| Rendered value | Flagship | Mid |
|---|---|---|
| Structurally parsed 7 of 7 | all `parsed_structurally` true | all true |
| Methodology and limitations 7 of 7 | all `has_methodology` and `has_limitations` true | all true |
| Key claims 35 / 33 | sum of `key_claims` = 35 | 33 |
| Claim word-support mean 0.94 / 0.95 | mean of 35 `claim_support` values = 0.9353 | mean of 33 = 0.9530 |
| Claim word-support minimum 0.82 / 0.85 | min = 0.8235 | min = 0.8462 |
| Mean summary latency 11,230 / 7,142 ms | mean `latency_ms` = 11230 | 7142 |
| Measured cost 7 papers $0.921 / $0.140 | sum `cost_usd` = 0.921130 | 0.139592 |

Per-paper measured summarization cost quoted in the cost paragraph: flagship
0.921130 / 7 = $0.1316, rendered $0.132; mid 0.139592 / 7 = $0.0199, rendered
$0.020.

## Model identity

The flagship tier requested and received `claude-opus-4-8` in every record.
The mid tier requested the alias `claude-haiku-4-5`; the summary study records
the returned snapshot `claude-haiku-4-5-20251001` in its per-paper rows while
the tier header records the requested alias. Chapter 4 uses the requested
alias throughout, which is the identifier the deployed configuration sets. No
rendered claim depends on the snapshot suffix.

## Cost estimates

Table 4-17 figures are list-price estimates, not measured spend, and every one
is reproduced by `ai_cost_recompute.py` from the price snapshot plus the
deployed caps. Prices are now cited in the chapter to their first-party
sources: `anthropicPricing2026`, `deepseekPricing2026`, and
`openaiEmbeddingSmall2026`, all reviewed 2026-07-26.

Two rounding corrections were applied during this pass so that the chapter
matches the script rather than an intermediate:

- One flagship paper summary: script yields $0.1006, which is $0.101 at three
  decimals. The chapter previously printed $0.100.
- Fifteen-case flagship evaluation run: script yields 0.0278 x 12 = $0.3336,
  which is $0.33. The chapter previously printed $0.34, the value obtained by
  multiplying the already-rounded $0.028 by twelve.

Daily capacities remain approximate in the chapter ("about fifty", "roughly
180", "roughly 250"); the exact integer quotients 49, 179, and 248 are now
stated alongside them. The same two corrections were propagated to the
"Figures this snapshot supports" paragraph of the price snapshot, whose price
table itself is unchanged.

## Claim-strength boundaries retained

- The public source-match state measures lexical anchoring in retrieved text.
  It does not establish semantic entailment or scientific correctness, and the
  chapter, digest, and conclusions all keep this qualifier attached.
- An out-of-range citation marker produces no verified citation record and
  cannot be displayed as evidence. The generated answer text is not rewritten.
  Chapter 4, Algorithm 4-3, and `appendix_1.tex` now agree on this wording.
- Both graded runs are single runs over one fifteen-case corpus. They
  characterize the declared cases and support no general claim about answer
  quality across models, prompts, or question distributions.
- The summary tier study measures schema completion and content-word overlap
  only. Human judgment of explanatory quality remains future evaluation.
