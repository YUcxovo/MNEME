# Demo Q&A Script (Milestone 5)

Owner: Yifan Zhang. Curated question set for the live presentation, with the
validation evidence behind each question and the exact re-validation
procedure to run before the demo.

The curated set lives in `backend/tests/fixtures/eval/qa_demo_v1.json`
(fixture version `qa-demo-v1`). It is a strict subset of the graded
`qa-seed-v2` corpus: six answerable questions spanning six of the seven
corpus papers, plus one deliberate out-of-scope question that demonstrates
the refusal contract. Reusing graded fixtures means every demo question has
recorded evidence behind it instead of a rehearsal impression.

## Curated questions

| # | Fixture | Paper | What the audience sees |
|---|---------|-------|------------------------|
| 1 | `qa-001-transformer-attention` | Attention Is All You Need (1706.03762v7) | Crisp grounded answer: multi-head self-attention replaces recurrence/convolutions, with tappable citations |
| 2 | `qa-002-lora-parameters` | LoRA (2106.09685v2) | Mechanism answer: frozen weights + low-rank matrices |
| 3 | `qa-004-rag-components` | RAG (2005.11401v4) | Meta moment: the app explains the retriever + generator architecture it itself uses |
| 4 | `qa-005-dpo-reward-model` | DPO (2305.18290v3) | Why-question: closed-form mapping removes the reward model |
| 5 | `qa-011-bert-pretraining` | BERT (1810.04805v2) | Enumeration answer: masked LM + next sentence prediction |
| 6 | `qa-012-vit-patches` | ViT (2010.11929v2) | Process answer: patches -> linear projection -> position embeddings |
| 7 | `qa-014-lora-diffusion-scope` | LoRA (2106.09685v2) | Honest refusal: the paper says nothing about image diffusion models, and the system says so instead of inventing an answer |

Suggested order: 1 -> 3 -> 7 -> any of the rest. Open with the iconic paper,
show the self-referential RAG answer, then demonstrate the refusal case
explicitly -- grounded refusal is the differentiating behavior, not a
failure, so present it on purpose.

## Validation provenance

All seven questions were part of the recorded live evaluation of
`qa-seed-v2` (2026-07-28, flagship route `claude-opus-4-8`, fifteen cases,
zero skips) reported in thesis Chapter 4. The raw run report is retained
on the repository `docs` branch as
`docs/evaluation/qa/qa-seed-v2-run-2026-07-28-opus.json`; the per-question
provenance below is traceable to that file:

- All six answerable questions above were answered with at least one
  verified citation and were fully source-matched under the 30% content-word
  criterion (12 of 12 answerable cases in the run).
- `qa-014-lora-diffusion-scope` followed the refusal protocol exactly. It is
  chosen over `qa-015-rag-clinical-scope`, which refused in prose but
  omitted the machine-readable marker in the recorded run.
- Mean end-to-end pipeline latency was ~4.7 s; budget for ~5 s of silence
  per question in the demo flow, or pre-warm the cache (below).

## Pre-demo re-validation

Run the graded harness over exactly the demo subset against the demo
backend (requires PostgreSQL/Redis with the pinned corpus ingested and a
valid Anthropic API key; the checked-in corpus pins exact arXiv revisions,
so a case is skipped rather than silently degraded if the wrong revision is
present):

```bash
cd backend
uv run python -m mneme.cli.run_qa_eval \
  --fixtures tests/fixtures/eval/qa_demo_v1.json \
  --output qa_demo_run.json
```

Acceptance criteria for a demo-ready system:

- `evaluated` = 7 with an empty `skipped` list (the CLI exits nonzero on
  zero evaluated cases, so an empty run cannot pass silently).
- 6 answered cases, each with `verified_citations` >= 1 and
  `source_match_status` = `matched`.
- 1 refusal (`qa-014`) with `refusal_correct` = true.

Because `/qa/ask` and the eval CLI share the completion cache (24 h TTL,
keyed on question + evidence + model + prompt version), a re-validation run
within 24 h of the presentation also pre-warms the exact demo answers: the
live demo then serves cached completions with sub-second generation time
and zero marginal spend. Asking the demo questions verbatim matters for the
cache hit.

## Fallbacks

- Provider outage during the demo: answers validated within 24 h are served
  from cache; questions outside the cache surface the standard
  `service_unavailable` error envelope rather than crashing the app.
- Backend unreachable: a live-configured Android build does not switch to
  controlled fixtures. It restores the last Room-cached briefing and paper
  content where available (surfaced with the cached data-source label) and
  shows the standard error state for anything not cached. The
  controlled-fixture mode is a separate, deliberate operator choice: a
  build with a blank demo token selects the fixture repository, which
  labels its content explicitly. Decide before the demo which build is on
  the device, and state the visible data-source label honestly.
