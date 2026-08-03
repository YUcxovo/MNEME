# Mneme Backend

FastAPI backend for the Mneme research assistant. The current checkout includes the data and AI platform, platform hardening, and a code-only production delivery layer: revision-safe arXiv/PDF ingestion, structured summarization, chunking, embeddings, retrieval, Q&A, recommendations, citation graphs, behavior profiles, durable ARQ orchestration, schedulers, bounded health and operations interfaces, explicit connection pools, production process configuration, deployment gates, backups, installation-local demo replay, and public API acceptance checks.

## Requirements

- Python 3.11-3.13 (the repository currently selects Python 3.12)
- uv
- PostgreSQL 16 with the pgvector extension
- Redis for ARQ, AI response caching, and the scheduling commands

## Setup

```bash
cd backend
uv sync --locked --dev
cp .env.example .env
uv run alembic upgrade head
```

All settings use the `MNEME_` prefix. `MNEME_DATABASE_URL` accepts both `postgresql://` and `postgresql+asyncpg://` URLs. `MNEME_DATABASE_POOL_SIZE`, `MNEME_DATABASE_MAX_OVERFLOW`, `MNEME_DATABASE_POOL_TIMEOUT_SECONDS`, and `MNEME_DATABASE_POOL_RECYCLE_SECONDS` apply uniformly to each API, worker, or CLI process. The default bound is at most 10 database connections per process (`5 + 5`), so deployment capacity planning must multiply that bound by the process count. Application construction is lazy and does not itself connect to PostgreSQL or Redis.

Document artifacts default to `.data/papers` and can be moved with `MNEME_PAPER_STORAGE_DIR`. Daily ingestion defaults to `cs.AI,cs.LG` with 20 results per category; override those values with `MNEME_ARXIV_DAILY_CATEGORIES` and `MNEME_ARXIV_DAILY_MAX_RESULTS`.

### Configure the demo identity

Protected endpoints require a pre-provisioned user UUID and only the SHA-256 digest of an opaque token. Keep the raw token outside git and the production Android source.

1. Run `uv run python -m mneme.cli.hash_demo_token`, enter a strong raw token at the hidden prompt, and set the printed digest as `MNEME_DEMO_TOKEN_SHA256` in `.env`.
2. Generate a UUID, set it as `MNEME_DEMO_USER_ID`, and provision the user rows.

```bash
uv run python -c "import uuid; print(uuid.uuid4())"
uv run python -m mneme.cli.bootstrap_demo_user
```

The bootstrap command is idempotent and never stores the raw token or overwrites existing preferences.

## Run the API and worker

Start the API and the ARQ worker in separate terminals:

```bash
uv run uvicorn mneme.main:app --reload
uv run arq mneme.tasks.worker.WorkerSettings
```

The worker registers metadata, PDF, parse, summarize, chunk, embed, and digest stages. It also scans for queued or stale revision-scoped dispatches at startup and once per minute. PostgreSQL is the durable source of job state; Redis carries execution attempts.

Available authenticated API routes include:

- `GET /v1/papers` and `GET /v1/papers/{paper_id}`
- `GET /v1/users/me/preferences` and `PUT /v1/users/me/preferences`
- `GET /v1/papers/{paper_id}/summary` (stored result or `202 Accepted` with the earliest missing revision stage)
- `GET /v1/jobs/{job_id}` (durable public job state without raw operational errors)
- `GET /v1/digests` and `POST /v1/digests/recommended`
- `POST /v1/qa/ask`

`GET /v1/health` is public process liveness and never waits for infrastructure. `GET /v1/health/ready` concurrently probes PostgreSQL and Redis within `MNEME_READINESS_TIMEOUT_SECONDS`; it returns a safe `503 service_unavailable` envelope if either required dependency is unavailable. Protected requests use `Authorization: Bearer <raw-token>`. Responses include `X-Request-ID`, and errors use the stable `ErrorResponse` shape without secrets, raw inputs, database diagnostics, or tracebacks.

## Prepare a production deployment

The provider-neutral templates under `deploy/templates/` and the complete operator sequence in [`deploy/README.md`](../deploy/README.md) cover Gunicorn with `uvicorn-worker`, loopback-only API binding, Nginx bootstrap/TLS configurations, migration units and a manual preflight gate, scheduled ingestion and briefings, validated PostgreSQL backups, private platform health checks, replayable demo preparation, and a public-API MVP smoke gate. They do not provision a VM, DNS, firewall, certificate, provider account, secret, off-host backup target, or alert destination.

Render a complete staging tree from the repository root without writing privileged host paths:

```bash
uv run --project backend python -m mneme.cli.render_deployment \
  --server-name api.example.edu \
  --output-dir /tmp/mneme-deployment
```

The renderer fails on an incomplete or unexpected template set. Replace every active required placeholder, leave unused optional examples commented, and install the result privately. Apply migrations and bootstrap the demo identity, then run `mneme-preflight.service` manually before enabling the API and worker. Its stable JSON report fails closed on unsafe configuration, unsupported service-timeout overrides, a stale migration, missing pgvector/Redis/storage, insufficient database connection headroom, unusable backup tooling or credentials, or a libpq backup service that does not reach the application database. Configuration-only `--offline` output is `incomplete` and exits nonzero. The long-running services depend on migration rather than preflight, so a failed manual gate is an operator stop condition rather than a runtime liveness dependency.

The packaged demo manifest can be inspected without touching the database or network:

```bash
uv run --project backend python -m mneme.cli.seed_demo --dry-run
```

The live seed command is resumable on one installation: it bootstraps the configured demo user, invokes the existing onboarding API, requires the original seed and all returned papers to become ready, replaces explicit preferences, posts stable manifest events, and verifies an exact persisted event set. When an existing onboarding digest contains a failed job, the request reclaims it only when its latest revision, current pipeline version, and current artifact/model identity still match. The result records `seed_paper_id`, `digest_paper_ids`, and `digest_arxiv_ids`; copy the seed UUID to the smoke configuration. The live onboarding candidates and provider-generated artifacts can vary across hosts or dates, so this is not a frozen cross-host fixture. It does not fabricate summaries, answers, embeddings, or citation edges.

After TLS and seeding, run the public API acceptance sequence from a trusted host. Supply the raw token through an owner-only file or `MNEME_MVP_SMOKE_TOKEN`, never a command-line argument:

```bash
export MNEME_MVP_SMOKE_BASE_URL=https://api.example.edu
export MNEME_MVP_SMOKE_SEED=1706.03762
export MNEME_MVP_SMOKE_PAPER_ID='<seed_paper_id from demo-seed-result-v1>'
export MNEME_MVP_SMOKE_QUESTION='What problem does this paper address, and what method does it propose?'
uv run --project backend python -m mneme.cli.smoke_backend --token-file /absolute/path/demo.token
```

The `mvp-smoke-report-v1` output checks liveness, readiness, authenticated preferences, exact catalog and summary identity, asynchronous summary jobs, recommended briefing generation, a connected graph, and optional source-matched Q&A whose citations belong to the tested paper. It contains no token or response body. Exit codes are `0` for a passing sequence, `1` for an acceptance failure, and `2` for invalid local configuration.

## Schedule ingestion and briefings

Schedule idempotent metadata jobs for the current UTC date and configured categories:

```bash
uv run python -m mneme.tasks.fetch_daily
```

Optional backfill controls are available through `--date YYYY-MM-DD`, repeated `--category`, and `--max-results`. The command creates one durable collection job per `(UTC date, category, pipeline version)`. Successful metadata ingestion persists exact arXiv revisions and fans out revision-scoped PDF jobs.

For a synchronous metadata-only smoke fetch, use `uv run python -m mneme.cli.fetch_arxiv cs.AI --max-results 20`. That manual command persists revisions but deliberately does not create downstream PDF jobs.

Schedule the demo user's current UTC-week Research Briefing:

```bash
uv run python -m mneme.tasks.assemble_weekly
```

Use `--week-start YYYY-MM-DD` for a Monday backfill. The command requires `MNEME_DEMO_USER_ID` and identifies work by `(user, Monday, generator version)`. Empty candidate sets are valid successful briefings, and repeated invocations do not duplicate work.

A simple production cron can invoke both commands daily while the ARQ worker runs continuously:

```cron
0 2 * * * cd /path/to/MNEME/backend && uv run python -m mneme.tasks.fetch_daily
15 2 * * * cd /path/to/MNEME/backend && uv run python -m mneme.tasks.assemble_weekly
```

Running the weekly command daily is intentional: the durable weekly identity makes it a safe recovery mechanism if Monday's Redis dispatch fails. Both CLIs emit machine-readable JSON and return a nonzero status on scheduling failure.

## Synchronize citation graphs

Synchronize both references and citations for one local paper by UUID or unversioned arXiv ID:

```bash
uv run python -m mneme.tasks.sync_semantic_graph --arxiv-id 2401.00001 --limit 50
uv run python -m mneme.tasks.sync_semantic_graph --paper-id <paper-uuid>
```

The client serializes requests, applies configured throttling and bounded retries, and paginates within the configured neighbor limit. A Semantic Scholar API key is optional but recommended for a stable individual limit. Observations with one unknown endpoint remain stored under the provider paper ID. After that paper enters the local catalog, a later graph-sync invocation that sees its provider identity resolves the stored observation. The public endpoint exposes only locally resolved nodes and never performs external synchronization during a GET request.

Seed onboarding uses the same provider and persistence boundaries automatically. It resolves
a bounded citation neighborhood for the supplied seed, validates the related arXiv records,
persists five neighbors and their real edges, and prepares the seed together with the five
briefing papers. A depth-two graph opened from any returned paper can therefore recover the
shared seed neighborhood. Candidate metadata is resolved in bounded batches; a failed batch
is retried as serialized single-paper requests on the same rate-limited client. If discovered
neighbor metadata remains unavailable, onboarding returns a retryable error rather than
silently replacing the graph-backed selection. If Semantic Scholar is unavailable or fewer
than five neighbors can be identified, onboarding uses the existing five-paper same-category
fallback without creating citation edges. Graph reads remain free of external provider calls.

`POST /v1/events` stores raw client UUIDs once and recomputes the active `behavior-v2` profile in the same PostgreSQL transaction. Event timestamps must be timezone-aware ISO 8601 values and cannot be more than five minutes ahead of the server clock; the recomputation query uses the same upper bound. The active model uses positive and negative channels, continuous opened-paper duration weighting, 14/60-day decay, per-paper saturation, exposure-gated skips, bounded confidence, a 180-day window, and latest-revision paper embeddings from the configured model. ADR 0003 freezes the parameters, while `behavior-v1` remains callable as the replay baseline.

Existing raw history can be replayed without inserting a synthetic event:

```bash
uv run python -m mneme.cli.recompute_behavior
uv run python -m mneme.cli.recompute_behavior --user-id <user-uuid>
```

The command stores no raw vector in its output; it reports safe model identity, confidence, channel availability, and aggregate evidence counts. A missing configured or stored user returns a stable exit status, and infrastructure errors do not expose database details.

## Inspect platform operations

Generate one bounded, read-only JSON snapshot from durable PostgreSQL state:

```bash
uv run python -m mneme.cli.report_platform
uv run python -m mneme.cli.report_platform --window-hours 48 --failed-limit 10
```

The `platform-operations-v1` payload reports windowed job creation and execution attempts, current queued/running work, undispatched and expired dispatch leases, durable worker-stage failures, paper processing and latest-revision parse quality, and digest generation. `--window-hours` is bounded to 1--720, `--dispatch-lease-seconds` to 1--86400, and `--failed-limit` to 0--100. Each recent failure includes `job_id`, the same opaque UUID accepted by the authenticated `GET /v1/jobs/{job_id}` contract, so an operator can correlate the report with public job state. Raw worker diagnostics and internal idempotency keys are never selected or emitted. Redis enqueue rejection is represented by structured logs and currently undispatched work, not mislabeled as a historical database counter.

Controlled behavior evaluation is offline and requires no PostgreSQL, Redis, provider, or user data. From `backend/`, use `uv run python -m mneme.cli.evaluate_behavior --output /tmp/mneme-behavior-evaluation` for an exploratory run. The retained clean-tree workflow, fixture, metrics, plots, and claim boundaries are documented in `docs/evaluation/behavior/README.md`.

## Pipeline and artifacts

The staged flow is `fetch_metadata -> download_pdf -> parse_pdf -> summarize_paper + chunk_paper -> embed_chunks -> assemble_digest`. Each paper-scoped stage receives both `paper_id` and `paper_version_id`; generated summaries, chunks, embeddings, provenance, and status reconciliation therefore cannot cross arXiv revisions.

Artifacts are installed atomically under:

```text
MNEME_PAPER_STORAGE_DIR/
`-- <paper-uuid>/
    `-- <paper-version-uuid>/
        |-- source.pdf
        `-- parsed.json
```

The downloader validates HTTP status, PDF media/signature, and the configured byte limit, then records the SHA-256 and download timestamp. The parser combines PyMuPDF text blocks with pdfplumber layout hints, restores logical single- or multi-column reading order, normalizes wrapped words, and writes the shared `ParsedDocument` JSON contract. Parse quality is `structured`, `text_only`, or `abstract_only`; unusable PDFs fall back to the stored arXiv abstract so downstream AI stages remain recoverable. The parser version participates in the durable parse identity, so a parser upgrade does not reuse an older parse job. PDF parsing is synchronous inside its bounded ARQ job because the parser libraries' supported runtime is more reliable in the worker thread than through an additional executor hop.

Durable jobs use input-derived idempotency keys, PostgreSQL uniqueness, dispatch leases, stable ARQ attempt IDs, and explicit `queued`, `running`, `succeeded`, or `failed` states. Completed stage output is reused, failed stages can be claimed for retry, and the latest paper revision becomes `ready` only after its required summary and embedded chunks exist; degraded artifacts produce `partial`.

## AI services

All live LLM access goes through `mneme.ai` (see `docs/architecture/ai-services.md`):
provider adapters for Anthropic, DeepSeek, and OpenAI; environment-backed task routing;
Redis completion caching; and a hard daily budget (`MNEME_AI_DAILY_BUDGET_USD`). Configure
the key selected by `MNEME_LLM_SUMMARY_MODEL` and `MNEME_LLM_QA_MODEL`. Tests use
deterministic fakes and make no external model call.

OpenAI remains the default embedding backend. A local CPU demo can instead use the optional
FastEmbed extra and BGE Small:

```bash
uv sync --extra local-embeddings
```

```dotenv
MNEME_DEEPSEEK_API_KEY=<deepseek-api-key>
MNEME_DEEPSEEK_THINKING_ENABLED=false
MNEME_LLM_SUMMARY_MODEL=deepseek-v4-flash
MNEME_LLM_QA_MODEL=deepseek-v4-flash
MNEME_AI_EMBEDDING_BACKEND=fastembed
MNEME_AI_LOCAL_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
MNEME_AI_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5+fastembed-pad1536-v1
```

The local model emits learned 384-dimensional dense vectors. The adapter L2-normalizes and
zero-pads them to the frozen `vector(1536)` store width; zero-padding preserves cosine
similarity and ordering. The qualified persisted model identity includes the adapter version,
so these values cannot be confused with native 1536-dimensional embeddings. This local path
is an explicit development/demo option; it is not enabled silently when an external provider
fails.

The evaluation fixture format and seed cases are documented in `docs/architecture/ai-evaluation.md`. Provider and model IDs are recorded with generated artifacts; they are configuration, not hard-coded architecture contracts.

## Database migrations

Alembic uses `MNEME_DATABASE_URL`. The migration chain creates the v0.1 pgvector schema, adds revision download/parse provenance and recoverable dispatch leases, then adds bidirectional Semantic Scholar citation identities plus traversal and unresolved-target resolution indexes.

```bash
uv run alembic upgrade head
uv run alembic check
uv run alembic downgrade base
uv run alembic upgrade head
```

After a model change, create and review a separate revision rather than editing an applied migration:

```bash
uv run alembic revision --autogenerate -m "describe the schema change"
```

## Checks

```bash
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run pyrefly check .
uv run pytest -m base
uv run pytest
```

Database integration and end-to-end pipeline tests run when `MNEME_DATABASE_URL` is configured. CI supplies a PostgreSQL 16 pgvector service automatically; deterministic fakes replace arXiv, Redis queue execution, and AI providers where appropriate.

## Current limitations

- The deployment package renders and validates host artifacts but does not provision or mutate a cloud host. VM/DNS/firewall/TLS setup, production secrets and provider choices, unit installation, and live Android integration remain operator work.
- Database backup creation verifies custom-archive readability and retention, not recoverability. A scratch restore, off-host encrypted copy, local PDF artifact policy, and restore rehearsal are required before disaster-recovery sign-off.
- Private health checks expose stable exit codes for systemd and fail on undispatched, stale-dispatched, or stale-running jobs. Their ingestion/digest timestamps measure stage-wide success rather than timer identity, so timer activation needs separate host evidence. The alert adapter is intentionally a commented placeholder until the deployment owner selects and tests a delivery channel.
- Packaged demo events are deterministic demonstration data, not user-study evidence. Replay is stable within a verified installation, but live onboarding candidates and provider-generated summaries, embeddings, answers, and graph observations are not frozen across hosts or dates.
- Authentication is a single-user demo mechanism; there is no login, JWT, or token lifecycle.
- Readiness covers the required PostgreSQL and Redis paths only; external paper and model providers remain visible through request/job failures and operational reports rather than blocking process readiness.
- Local document storage must be mounted at the same path for every API/worker process; distributed object storage and garbage collection are deferred.
- The worker's automatic recovery scan can reconstruct revision-scoped jobs. Collection-level daily and weekly jobs are recovered by repeatable CLI invocations because their hashed durable identities do not contain reconstructable arguments.
- The Android skeletal path can call the backend through Retrofit/OkHttp when its demo
  token is configured; real WorkManager background sync remains unfinished.
- Seed onboarding prepares its bounded citation neighborhood automatically. Synchronization
  for papers entering through other paths remains an explicit single-paper CLI; fleet-wide
  scheduling is deferred.
- Behavior profiles recompute on `/events` or through the explicit replay command. Automatic replay after embeddings arrive or solely because events age is not scheduled; production operations must invoke replay when that refresh is required. Any semantic tuning requires a new model identity and a separately frozen evaluation.
- Public graphs include only locally resolved citation endpoints; unresolved provider observations remain server-side until their papers are ingested and a later graph synchronization sees the matching provider identity.

## Layout

```text
backend/
|-- alembic/            # Async migration environment and versioned revisions
|-- src/mneme/
|   |-- ai/             # Providers, RAG services, routing, budget, cache, evaluation
|   |-- api/            # Routers, dependencies, schemas, middleware, shared errors
|   |-- cli/            # Demo identity, operations, replay, evaluation, and manual tools
|   |-- core/           # Settings, logging, and security helpers
|   |-- db/             # Async engine, sessions, and FastAPI dependencies
|   |-- models/         # SQLAlchemy persistence model
|   |-- repositories/   # Transactions, artifacts, jobs, catalog, and digest queries
|   |-- evaluation/     # Controlled behavior fixtures, metrics, replay, and reporting
|   |-- services/       # External clients, documents, recommendation, and orchestration
|   |-- redis/          # Shared Redis and ARQ configuration
|   |-- tasks/          # Workers, durable stages, recovery, and cron-friendly CLIs
|   `-- main.py         # Application factory and ASGI app
|-- tests/              # Unit, contract, migration, DB, and deterministic E2E tests
|-- pyproject.toml      # Dependencies and tool configuration
`-- uv.lock             # Reproducible dependency lock
```
