# Pipeline, Evaluation, and Reliability

## Idempotent Pipeline Stages

Do not implement one monolithic `PaperPipelineJob`. Use separately retryable ARQ jobs:

1. `fetch_metadata`
2. `download_pdf`
3. `parse_pdf`
4. `summarize_paper`
5. `chunk_paper`
6. `embed_chunks`
7. `assemble_digest`

Every stage checks its persisted input hash and successful output before doing work. A retry
must not duplicate rows or repeat completed provider calls. `pipeline_jobs` records stage,
status, attempts, error, timestamps, and pipeline version.

## RAG Evidence Labels

- `source_matched`: every cited source came from the retrieved chunks.
- `citation_coverage`: major answer claims contain a source reference.
- `entailment_checked`: reserved for a later semantic support check.

The MVP UI says "Sources matched", never "Verified answer". If evidence is insufficient,
the system refuses to answer instead of fabricating a citation.

## Evaluation Schedule

- M1: freeze metric definitions and evaluation fixture format.
- M2: create 5 manually checked QA cases while validating parsing/chunking.
- M3: expand to 10-20 cases and run retrieval/citation regression tests.
- M4: report final results and tune prompts/parameters.

Required metrics: parse success rate, retrieval recall@k, citation source-match rate,
human answer-helpfulness score, digest relevance score, latency, and per-paper cost.

## Demo Mode

Demo mode is explicit configuration, not hidden endpoint behavior. It uses pre-seeded,
license-compatible fixtures when external systems fail:

- cached arXiv metadata and selected PDFs;
- pre-generated summaries and Q&A;
- a stored Semantic Scholar citation graph;
- Room-cached Android demo flow;
- local/backend health indicators showing whether data is live or seeded.

## Observability

No custom monitoring dashboard is in MVP scope. Use structured logs, persisted job status,
health endpoints, and CLI/SQL reports for fetch volume, parse success, ARQ failures, LLM
usage/cost, and digest generation. Production alerts cover service uptime, disk/memory, and
daily ingestion failure.
