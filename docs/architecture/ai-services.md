# AI Service Foundation (Milestone 1)

Owner: Yifan Zhang. This document describes the `mneme.ai` package: the LLM
provider abstraction, model routing, the budget guard, the completion cache
policy, and the evaluation harness skeleton. Endpoint contracts stay frozen in
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
  (Messages API) and OpenAI (Chat Completions), plus `FakeLLMProvider` for
  tests and evaluation. Vendor exceptions are mapped to `LLMProviderError`
  with a `retryable` flag (429/5xx/connection errors are retryable).
- Providers are only registered when their API key is configured; routing to
  an unregistered provider raises `ProviderNotConfiguredError`, which AI
  endpoints will map to `service_unavailable`.

## Model routing

`ModelRouter` maps each `AITask` (`summarize`, `qa`) to one model configured
via settings (`MNEME_LLM_SUMMARY_MODEL`, `MNEME_LLM_QA_MODEL`). The provider
is inferred from the model name (`claude-*` -> Anthropic, `gpt-*`/`o*-` ->
OpenAI) and validated at startup so typos fail before the first request.
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

## AI endpoints (Milestone 1 state)

`GET /v1/papers/{paper_id}/summary` is implemented against the frozen
contract with a deterministic placeholder (first two abstract sentences,
`status=partial`, `source_match_status=not_checked`). Milestone 2 replaces
the internals with cached/async LLM generation (202 + Job) behind the same
schema. Shared AI dependencies live in `mneme.api.dependencies.ai`.
