# AI Services (Milestones 1-3)

Owner: Yifan Zhang. This document describes the `mneme.ai` package: the LLM
provider abstraction, model routing, the budget guard, the completion cache
policy, the evaluation harness, and the Milestone 2/3 pipelines built on top
(summarization, chunking, embeddings, retrieval, grounded Q&A,
recommendations, and graph algorithms). Endpoint contracts stay frozen in
`docs/api/openapi-v0.1.yaml`; this file covers implementation policy only.

## Provider abstraction

Every LLM call in the backend goes through `mneme.ai.service.LLMService`.
Nothing else imports a vendor SDK.

```
CompletionRequest --> ModelRouter --> LLMCache --> BudgetGuard --> LLMProvider
      (task)          (task->model)    (hit? return)  (hard cap)     (SDK call)
                                                            |
                              CompletionResult <-- pricing + telemetry
```

- `mneme.ai.types.CompletionRequest` is provider-agnostic: task, messages,
  optional system prompt, output-token cap, and a `prompt_version` string.
- `mneme.ai.providers` implements the `LLMProvider` protocol for Anthropic
  (Messages API), DeepSeek (its OpenAI-compatible Chat Completions API), and
  OpenAI (Chat Completions), plus `FakeLLMProvider` for tests and evaluation.
  Vendor exceptions are mapped to `LLMProviderError` with a `retryable` flag
  (429/5xx/connection errors are retryable). DeepSeek thinking is disabled by
  default for predictable demo latency and cost, with an environment override.
- Providers are only registered when their API key is configured; routing to
  an unregistered provider raises `ProviderNotConfiguredError`, which AI
  endpoints will map to `service_unavailable`.

## Model routing

`ModelRouter` maps each `AITask` (`summarize`, `qa`) to one model configured
via settings (`MNEME_LLM_SUMMARY_MODEL`, `MNEME_LLM_QA_MODEL`). The provider
is inferred from the model name (`claude-*` -> Anthropic, `deepseek-*` ->
DeepSeek, `gpt-*`/`o*-` -> OpenAI) and validated at startup so typos fail
before the first request.
Defaults target `claude-opus-4-8`; swap to a cheaper model per-environment
without code changes.

## BudgetGuard (hard daily cap)

- Spend is tracked in Redis under `mneme:ai:budget:<utc-date>` via
  `INCRBYFLOAT`, so the cap is shared across API workers and the ARQ worker.
- Before each provider call the service checks the counter against
  `MNEME_AI_DAILY_BUDGET_USD` (default 5 USD) and raises
  `BudgetExceededError` once reached. Cache hits are always served.
- Costs come from the static price table in `mneme.ai.pricing`; unknown
  models are charged at the most expensive tier so the guard never
  undercounts. Keys expire after 48 hours.
- The check-then-spend pair is not atomic: concurrent requests can overshoot
  the cap by at most one in-flight completion each, which is acceptable for a
  daily stop-loss.

## LLM cache policy

Backed by Ruiyu's shared Redis client (`mneme.redis`), no second connection
pool.

- **Keys**: `mneme:ai:cache:<task>:<prompt_version>:<sha256(body)>` where the
  hashed body is canonical JSON of task, provider, model, prompt version,
  system prompt, messages, and the output-token cap. Any input change misses
  cleanly; identical requests hit deterministically.
- **TTL**: per task -- summaries 7 days (`MNEME_AI_SUMMARY_CACHE_TTL_SECONDS`),
  QA answers 24 hours (`MNEME_AI_QA_CACHE_TTL_SECONDS`). Summaries are
  version-keyed and effectively immutable; QA answers rotate faster because
  retrieval context will change as ingestion grows.
- **Invalidation**:
  1. Implicit -- bumping a prompt template's `prompt_version` changes every
     key, so old entries simply age out.
  2. Explicit -- `LLMCache.invalidate(task=..., prompt_version=...)` deletes by
     key pattern (SCAN-based; fine at demo scale).
  3. Corrupt entries are deleted on read and treated as misses.
- Cache hits are returned with `cached=true` and logged, so hit rates are
  measurable from structured logs.

## Evaluation harness skeleton

- Fixture format is frozen in `docs/architecture/ai-evaluation.md`; the first
  five QA fixtures live at `backend/tests/fixtures/eval/qa_seed_v1.json`.
- `mneme.ai.evaluation.EvaluationHarness` drives an async answer function
  over a fixture set and reports per-case and aggregate telemetry: keyword
  coverage (M1 placeholder metric), input/output tokens, estimated cost, and
  latency. The answer function is the seam where the real RAG pipeline plugs
  in at M3 without harness changes.
- `FakeLLMProvider` supplies deterministic, network-free responses so the
  harness and its tests run in CI.

## Summarization (Milestone 2)

- `mneme.ai.prompts` holds versioned templates. Bumping a prompt version
  invalidates cached generations implicitly and changes the stored
  `prompt_version` on new summaries.
- `SummarizationService` requests strict JSON (`tldr`, `key_claims`,
  `methodology`, `limitations`), parses it tolerantly (markdown fences are
  stripped), and degrades to a `status=partial` summary derived from the raw
  completion when parsing fails -- the pipeline never crashes on a
  malformed generation, and cost telemetry is still recorded.
- Summaries generated from parsed full text are `ready`; abstract-only
  fallbacks are `partial`. Idempotency key: SHA-256 of (title, truncated
  input, prompt version), enforced against `paper_summaries` before any
  provider call.
- The manually checked summarization seed lives at
  `backend/tests/fixtures/eval/summary_seed_v1.json` next to the M1 QA seed.

## Chunking and embeddings (Milestone 2)

- `mneme.ai.chunking` consumes the parse stage's section list and produces
  deterministic drafts: section titles and page ranges preserved, oversized
  sections split at sentence boundaries with token overlap, content hashed
  for idempotent embedding.
- `mneme.ai.embeddings` wraps both the OpenAI Embeddings API and an opt-in local
  FastEmbed/ONNX backend behind an `EmbeddingProvider` protocol (deterministic
  fake included). OpenAI `text-embedding-3-small` remains the default and emits
  1536 dimensions matching the pgvector schema.
- The local demo route uses `BAAI/bge-small-en-v1.5`. Its learned 384-dimensional
  vectors are L2-normalized and zero-padded to 1536 dimensions. Appending zeros
  preserves cosine similarity and ranking, avoids a schema migration, and is
  recorded under the qualified identity
  `BAAI/bge-small-en-v1.5+fastembed-pad1536-v1`. The model package is optional
  and must be installed/configured explicitly; provider failures never trigger
  a silent fallback.
- Batches are bounded (`MNEME_AI_EMBEDDING_BATCH_SIZE`) and every batch passes
  through the shared BudgetGuard, so external embedding spend counts against
  the same daily cap as completions. The local model has zero external cost.
- Pipeline stages (`mneme.ai.pipeline`) are consumed as ARQ jobs
  (`mneme.tasks.ai_jobs`): `summarize_paper`, `chunk_paper` (which enqueues
  `embed_chunks`), and `embed_chunks`. Stages are idempotent and resumable;
  retryable provider errors propagate to ARQ's retry policy, terminal
  failures are recorded on the durable `pipeline_jobs` row with a stable
  error code.

## Summary endpoint (Milestone 2)

`GET /v1/papers/{paper_id}/summary` serves the stored structured summary
(200) or creates one durable job per paper, enqueues the summarize stage,
and returns 202 + Job. Repeated requests reuse the pending job; failed jobs
are requeued on the next client retry. AI failures map to stable codes:
`ai_budget_exhausted` (429), `ai_provider_unconfigured` / `ai_provider_error`
(503).

## Retrieval and grounded Q&A (Milestone 3)

- `RetrievalService`: embed the question, run a pgvector cosine ANN search
  scoped to one paper, and append the first two document chunks as bounded
  overview anchors when they are not already dense hits. The anchors improve
  paper-level recall without displacing question-specific top-k
  (`MNEME_AI_RETRIEVAL_TOP_K`) evidence.
- `mneme.ai.qa.rerank` blends vector similarity (0.7) with question/chunk
  content-word overlap (0.3). This is an honest lexical rerank, not a
  cross-encoder; the seam allows swapping one in later. Reranking keeps
  overview anchors after the configured question-specific evidence rather
  than forcing them into its slots.
- `GroundedAnswerService` refuses without an LLM call when there is no
  evidence or the best reranked score is below
  `MNEME_AI_QA_MIN_EVIDENCE_SCORE`, prompts with numbered excerpts plus their
  section/page context, and requires bracketed citation markers. The provider
  must return either a cited answer or the exact refusal sentinel; an answer
  is not discarded merely because a provider incorrectly appends that
  sentinel on a separate line. `verify_citations` drops markers that
  point outside the evidence and checks each citation-bearing local claim
  against its corresponding chunk using content-word overlap:
  all citations matched -> `matched`, some -> `partial`, none ->
  `insufficient_evidence`. A model-declared `INSUFFICIENT_EVIDENCE` becomes
  a stable refusal answer.
- `POST /v1/qa/ask` persists both turns of the exchange (with citations and
  generation telemetry) in `qa_conversations` / `qa_messages` and returns
  the frozen `Answer` schema. Papers without embedded chunks get the stable
  refusal with `insufficient_evidence`, not an error.

## Recommendations

- `mneme.ai.recommendation` scores candidates against the frozen `user_preferences` interface. Explicit topic match has nominal weight 0.45, recency with a one-week half-life has weight 0.20, and behavior has weight 0.35. For model version 2, positive and negative cosine similarities form the bounded affinity `0.5 + 0.5 * (positive - negative)`, and the behavior weight is multiplied by profile confidence before available weights are normalized. Zero-confidence profiles therefore follow the cold-start path. Version 1 retains its original positive-vector cosine semantics for replay.
- Recommendation reasons include behavior only when positive similarity exceeds negative similarity; avoidance evidence cannot be presented as a reason to read a paper. Scores remain in `[0, 1]`, and equal scores retain the UUID tie-break.
- `POST /v1/digests/recommended` reuses a digest generated in the last 24 hours only when its preference-model version and `recommender-v2` generator identity match the active state. Otherwise it scores synchronously without an LLM call and stores an immutable `manual` digest snapshot. Candidate selection prefers the configured recent window. If that window is empty, a manual refresh ranks the processed catalog so an older seed library can still respond to explicit interest changes. Scheduled weekly generation retains its recent-window boundary. The contract's 202 branch stays reserved for a future slow path.
- The controlled comparison, ablations, metrics, and evidence limits are defined in `docs/evaluation/behavior/README.md`. The evaluation calls the production profile and scorer rather than duplicating their formulas.

## Knowledge-graph algorithms (Milestone 3)

`mneme.graph.algorithms` is pure and database-free, called by Ruiyu's graph
framework: citation-edge weighting damped by target in-degree, keyword
co-occurrence edges by Jaccard over title/category keywords, deterministic
weighted label propagation for clusters, weighted-degree rank scores
normalized to [0, 1], and bounded best-first subgraph selection (one seed
for paper-centered graphs, the user's engaged papers as seeds for user
subgraphs). `build_graph_view` composes these into the frozen `Graph`
response shape.

## Shared AI endpoint plumbing

Shared dependencies live in `mneme.api.dependencies.ai`: the app-scoped
LLM service, embedding service, ARQ enqueue pool, per-request repositories,
and `map_ai_error`, which translates AI-layer failures into the stable
error envelope.
