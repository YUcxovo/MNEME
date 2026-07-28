# Pipeline, Evaluation, and Reliability

## Runtime Topology

System cron invokes small scheduling CLIs, PostgreSQL stores durable pipeline state and artifact metadata, Redis/ARQ carries execution attempts, and one or more ARQ workers execute the stages. The API can also resume a paper's earliest missing stage through `GET /papers/{paper_id}/summary`; `GET /jobs/{job_id}` exposes the resulting durable state.

PostgreSQL is authoritative when Redis and database state disagree. Queue submission is never treated as durable completion.

## Staged Pipeline

Do not implement one monolithic `PaperPipelineJob`. The separately retryable stages are:

1. `fetch_metadata` fetches one arXiv category/date collection, persists every observed revision, and creates download children.
2. `download_pdf` validates and atomically stores the exact revision's source PDF, then creates its parse child.
3. `parse_pdf` extracts a versioned `ParsedDocument`, records provenance and quality, then creates independent summary and chunk children.
4. `summarize_paper` stores a structured summary for the exact revision.
5. `chunk_paper` replaces that revision's deterministic section-aware chunks and creates the embedding child.
6. `embed_chunks` stores model-labelled vectors for that revision's chunks.
7. `assemble_digest` builds an immutable weekly Research Briefing for one user and UTC Monday.

The summary and chunk branches may run concurrently after parsing. Processing status reconciliation serializes on the paper row and only evaluates the latest observed revision. A revision is `ready` when it has a non-degraded ready summary plus at least one chunk and every chunk is embedded; otherwise completed degraded work is `partial`.

## Revision and Artifact Boundaries

Every paper-scoped worker receives both `paper_id` and `paper_version_id`. Jobs validate that pair against the stored foreign-key relationship before reading or writing artifacts. Summaries, chunks, retrieval, Q&A, candidate selection, and status reconciliation must query by revision rather than accepting any artifact attached to the same paper work.

Document artifacts use deterministic UUID-only paths:

```text
<paper-storage-root>/<paper-id>/<paper-version-id>/source.pdf
<paper-storage-root>/<paper-id>/<paper-version-id>/parsed.json
```

Writes use a temporary file, `fsync`, and atomic replacement. `paper_versions` records download SHA-256/size/time and parse SHA-256/parser-version/quality/time. The parsed JSON carries a schema version, exact paper/revision IDs, source checksum, page count, ordered sections, page ranges, quality tier, fallback reason, and UTC timestamp.

The downloader accepts only bounded PDF responses with a valid signature and retries transient transport, `429`, and `5xx` failures. The parser combines PyMuPDF text blocks with pdfplumber layout hints. It reconstructs block text from positioned words, orders two-column pages by logical column flow, retains block boundaries, removes database-unsafe control characters, and detects numbered, Roman-numeral, and lettered section headings. Chunking repeats the control-character check so sidecars produced by an older parser remain safe to persist. Its quality tiers are:

- `structured`: useful extracted text with credible section structure.
- `text_only`: useful text with degraded or incomplete structure.
- `abstract_only`: the downloaded PDF is unusable, so the stored arXiv abstract becomes the single downstream section.

PDF parsing runs synchronously within its bounded ARQ job. An additional executor hop caused unsupported runtime interactions between the parser libraries; stage-level worker concurrency and the configured job timeout remain the resource boundary.

## Durable Identity and State

Every `pipeline_jobs.idempotency_key` is a SHA-256 of canonical JSON containing pipeline version, stage, scope, and material inputs. Current identities include:

- metadata: arXiv category and UTC run date;
- download: paper/revision IDs plus arXiv ID and revision number;
- parse: paper/revision IDs plus source PDF checksum and parser version;
- summarize and chunk: paper/revision IDs plus parsed checksum and parser version;
- embed: the parsed-artifact identity plus embedding model;
- weekly digest: user ID, UTC Monday, and generator version.

The database uniqueness constraint makes concurrent `get_or_create` calls converge on one durable job. An existing key is rejected if its stage, paper/revision scope, or pipeline version conflicts with the request.

Public states are `queued`, `running`, `succeeded`, and `failed`. Attempts, safe error code, internal last error, dispatch/start/finish timestamps, and pipeline version are persisted. The public API returns the safe code and timestamps but never `last_error`.

## Dispatch and Recovery

Before submitting to Redis, a scheduler atomically claims a PostgreSQL dispatch lease and increments the attempt. The ARQ attempt ID is derived from the durable job UUID and attempt number, so duplicate submissions for one attempt collapse at the broker. A submission failure releases the lease; an executing worker claims the matching durable job before side effects and records success or a stable failure code afterward.

Failed jobs can be claimed back to `queued`. The worker runs `recover_revision_dispatches` at startup and once per minute to submit queued or stale revision-scoped jobs. The summary API uses the same claim/release protocol when it resumes download, parse, or summary work.

Collection identities are deliberately hashed and do not contain reconstructable worker arguments. Automatic recovery therefore handles revision-scoped jobs only. Cron must invoke the daily and weekly CLIs repeatedly; their durable identities make those invocations safe and recover Redis dispatch failures without duplicate results.

## Scheduling Contracts

`python -m mneme.tasks.fetch_daily` schedules one metadata job per configured category for the current UTC date. `--date`, repeated `--category`, and `--max-results` support bounded backfills. Successful metadata work returns exact persisted revision identities and fans out download jobs.

`python -m mneme.tasks.assemble_weekly` schedules one Research Briefing for the configured demo user and current UTC Monday. `--week-start` accepts an explicit Monday. The candidate query considers the configured recent window before the exclusive next-Monday cutoff, includes only the latest `ready` or `partial` revision with a current summary, and averages current-revision embeddings for scoring. An empty candidate set is a successful immutable digest.

Both commands emit sorted JSON and return nonzero on validation, database, or queue failure. Run the daily command once per day and run the weekly command once per day as an idempotent recovery policy, even though only one weekly identity is created.

Seed onboarding adds one bounded synchronous preparation path for the first reading
session. It resolves five arXiv citation neighbors for the supplied seed, persists the real
provider edges, and dispatches the seed plus those five papers through the existing
revision-scoped jobs. The endpoint waits for usable terminal paper states before returning
the five-entry briefing. arXiv metadata is requested in bounded groups, and a failed group is
retried as serialized single-paper requests without discarding the already discovered
citation identities. Exhausted metadata recovery returns a retryable upstream error rather
than a successful briefing without the prepared graph. Semantic Scholar unavailability or
an insufficient citation neighborhood selects the existing same-category fallback; it does
not create inferred citation edges.

## Failure Semantics

- Transport validation, parsing, provider, persistence, and orchestration failures are stored with stable stage-specific codes.
- Retrying a succeeded input identity reuses its output and does not repeat provider calls.
- Retrying a failed identity starts a new dispatch attempt without changing its durable job UUID.
- A queue outage never marks work succeeded. The API returns `503 queue_unavailable`; scheduler CLIs return nonzero and can be rerun.
- Abstract-only parsing keeps the flow available but marks the paper `partial` rather than overstating document quality.
- A newer arXiv revision never reads an older revision's summary, chunks, embeddings, or Q&A evidence.

## RAG Evidence Labels

- `source_matched`: every cited source came from the retrieved chunks.
- `citation_coverage`: major answer claims contain a source reference.
- `entailment_checked`: reserved for a later semantic support check.

The MVP UI says "Sources matched", never "Verified answer". If evidence is insufficient, the system refuses to answer instead of fabricating a citation.

## Evaluation Schedule

- M1: freeze metric definitions and evaluation fixture format.
- M2: create 5 manually checked QA cases while validating parsing/chunking.
- M3: keep the existing seed fixtures as deterministic retrieval/citation regressions while completing the server-side integration path.
- M4: expand to 10-20 manually checked cases, report final results, and tune prompts/parameters.

Required metrics are parse success rate, retrieval recall@k, citation source-match rate, human answer-helpfulness score, digest relevance score, latency, and per-paper cost. The deterministic end-to-end test proves orchestration and persistence without making external arXiv, Redis-worker, or model calls; it is not a substitute for the manual quality evaluation.

## Demo Mode

Demo mode is explicit configuration, not hidden endpoint behavior. It uses pre-seeded, license-compatible fixtures when external systems fail:

- cached arXiv metadata and selected PDFs;
- pre-generated summaries and Q&A;
- a stored Semantic Scholar citation graph;
- Room-cached Android demo flow;
- local/backend health indicators showing whether data is live or seeded.

## Observability

No custom monitoring dashboard is in MVP scope. Use structured logs, persisted job status, `GET /jobs/{job_id}`, health endpoints, CLI JSON, and SQL reports for fetch volume, parse quality, dispatch attempts, ARQ failures, LLM usage/cost, and digest generation. Production alerts cover service uptime, disk/memory, document-storage capacity, and daily ingestion failure.
