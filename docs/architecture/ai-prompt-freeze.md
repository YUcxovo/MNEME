# AI Prompt and Routing Freeze (Milestone 5)

Owner: Yifan Zhang. This document records the frozen state of every prompt
template and default model route shipped for the demo, and the change
control that keeps the recorded evaluations valid.

## Frozen prompt templates

| Template | Version | Defined in |
|----------|---------|------------|
| Structured summarization system prompt | `summary-v1` | `mneme/ai/prompts.py` (`_SUMMARY_SYSTEM`) |
| Grounded Q&A system prompt | `qa-v2` | `mneme/ai/prompts.py` (`_QA_SYSTEM`) |

`backend/tests/test_prompt_freeze.py` pins both version constants, the
SHA-256 of both system templates, and the exact constructed request form of
`build_summary_request` and `build_qa_request` (task, system template,
user-message layout, and role sequence against representative inputs), so
the freeze covers the complete observable prompt, not only the system
half. The prompt version participates in every
completion cache key and in the generation-identity rows of
`paper_summaries` / `qa_messages`, so bumping the version is the only
sanctioned way to change observable behavior; the freeze test turns a
silent template edit into a CI failure.

Known open item carried past the freeze: the refusal-marker contract missed
one of three unanswerable cases in the recorded run (prose refusal without
the machine-readable marker). The fix is a `qa-v3` candidate after the
demo, not an edit to `qa-v2`.

## Frozen default model routing

| Task | Default model | Basis |
|------|---------------|-------|
| `summarize` | `claude-haiku-4-5` | Recorded structural tier study over all 7 corpus papers: 7/7 parsed into the full schema, claim word-support 0.95 mean / 0.85 min (flagship: 0.94 / 0.82), 6.6x cheaper, ~2/3 latency |
| `qa` | `claude-opus-4-8` | Recorded tier comparison: mid tier answered all 3 unanswerable questions in prose (refusal-marker adherence 0 of 3, vs 2 of 3 on flagship); grounding quality is user-visible |
| embeddings | `text-embedding-3-small` (OpenAI backend) or `BAAI/bge-small-en-v1.5` + fastembed pad-1536 (local backend) | unchanged; embedding model identity is stored per chunk |

This resolves finding F1 of `ai-cost-audit.md`: the audit recommended
routing bulk summarization off the flagship tier pending an eval
comparison, and the Milestone 4 tier study is that comparison. Both routes
stay environment-overridable (`MNEME_LLM_SUMMARY_MODEL`,
`MNEME_LLM_QA_MODEL`); the freeze covers the shipped defaults.

## Models used in the recorded evaluations

| Run (2026-07-28) | Model | Result summary |
|------------------|-------|----------------|
| `qa-seed-v2` graded run, flagship | `claude-opus-4-8` | 15/15 evaluated, citation rate 1.00, source-match 1.00, cost $0.326 |
| `qa-seed-v2` graded run, mid tier | `claude-haiku-4-5` | 11/12 full + 1 partial source match, refusal marker 0/3, cost $0.054 |
| Summary tier study, flagship | `claude-opus-4-8` | 7/7 parsed, claim support 0.94/0.82, cost $0.921 |
| Summary tier study, mid tier | `claude-haiku-4-5` | 7/7 parsed, claim support 0.95/0.85, cost $0.140 |

Full graded results are reported in thesis Chapter 4 (Tables `qa-eval`,
`qa-tiers`, `summary-tiers`). The raw run reports are retained on the
repository `docs` branch as
`docs/evaluation/qa/qa-seed-v2-run-2026-07-28-{opus,haiku}.json` and
`docs/evaluation/summaries/summary-tier-study-2026-07-28.json`.

## Change control after the freeze

1. Any template edit bumps the `*_PROMPT_VERSION` constant and updates the
   pinned hash in `test_prompt_freeze.py` in the same commit.
2. A `qa` template or route change requires re-running
   `python -m mneme.cli.run_qa_eval` on `qa_demo_v1.json` (see
   `docs/demo/qa-demo-script.md`) before the demo.
3. A `summarize` template or route change requires re-checking structured
   parsing on the corpus before bulk re-summarization spends budget.
