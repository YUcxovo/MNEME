# Mneme Backend

FastAPI backend for the Mneme research assistant. The current checkout includes the Milestone 1 platform and AI foundations plus the Milestone 2 revision-safe document pipeline: arXiv metadata ingestion, PDF download and parsing, structured summarization, chunking, embeddings, durable ARQ orchestration, daily ingestion scheduling, weekly Research Briefing assembly, and authenticated job/result APIs.

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

All settings use the `MNEME_` prefix. `MNEME_DATABASE_URL` accepts both `postgresql://` and `postgresql+asyncpg://` URLs. Application construction is lazy and does not itself connect to PostgreSQL or Redis.

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

`GET /v1/health` is public process liveness. Protected requests use `Authorization: Bearer <raw-token>`. Responses include `X-Request-ID`, and errors use the stable `ErrorResponse` shape without secrets, raw inputs, database diagnostics, or tracebacks.

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

The downloader validates HTTP status, PDF media/signature, and the configured byte limit, then records the SHA-256 and download timestamp. The parser combines PyMuPDF text extraction with pdfplumber layout hints and writes the shared `ParsedDocument` JSON contract. Parse quality is `structured`, `text_only`, or `abstract_only`; unusable PDFs fall back to the stored arXiv abstract so downstream AI stages remain recoverable. PDF parsing is synchronous inside its bounded ARQ job because the parser libraries' supported runtime is more reliable in the worker thread than through an additional executor hop.

Durable jobs use input-derived idempotency keys, PostgreSQL uniqueness, dispatch leases, stable ARQ attempt IDs, and explicit `queued`, `running`, `succeeded`, or `failed` states. Completed stage output is reused, failed stages can be claimed for retry, and the latest paper revision becomes `ready` only after its required summary and embedded chunks exist; degraded artifacts produce `partial`.

## AI services

All live LLM access goes through `mneme.ai` (see `docs/architecture/ai-services.md`): provider adapters for Anthropic and OpenAI, environment-backed task routing, Redis completion caching, and a hard daily budget (`MNEME_AI_DAILY_BUDGET_USD`). Configure the provider key selected by `MNEME_LLM_SUMMARY_MODEL` and configure `MNEME_OPENAI_API_KEY` for the current embedding provider. Tests use deterministic fakes and make no external model call.

The evaluation fixture format and seed cases are documented in `docs/architecture/ai-evaluation.md`. Provider and model IDs are recorded with generated artifacts; they are configuration, not hard-coded architecture contracts.

## Database migrations

Alembic uses `MNEME_DATABASE_URL`. The migration chain creates the v0.1 pgvector schema, adds revision download/parse provenance, and adds recoverable job dispatch leases.

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

- Authentication is a single-user demo mechanism; there is no login, JWT, or token lifecycle.
- `GET /v1/health` reports process liveness and does not probe PostgreSQL or Redis.
- Local document storage must be mounted at the same path for every API/worker process; distributed object storage and garbage collection are deferred.
- The worker's automatic recovery scan can reconstruct revision-scoped jobs. Collection-level daily and weekly jobs are recovered by repeatable CLI invocations because their hashed durable identities do not contain reconstructable arguments.
- The backend pipeline is usable independently, but the Android skeletal demo is not yet connected through Retrofit/OkHttp or a real WorkManager sync.
- Semantic Scholar ingestion, behavioral event updates, and graph persistence/API remain Milestone 3 work.

## Layout

```text
backend/
|-- alembic/            # Async migration environment and versioned revisions
|-- src/mneme/
|   |-- ai/             # Providers, RAG services, routing, budget, cache, evaluation
|   |-- api/            # Routers, dependencies, schemas, middleware, shared errors
|   |-- cli/            # Demo identity and manual arXiv tools
|   |-- core/           # Settings, logging, and security helpers
|   |-- db/             # Async engine, sessions, and FastAPI dependencies
|   |-- models/         # SQLAlchemy persistence model
|   |-- repositories/   # Transactions, artifacts, jobs, catalog, and digest queries
|   |-- services/       # External clients, documents, recommendation, and orchestration
|   |-- redis/          # Shared Redis and ARQ configuration
|   |-- tasks/          # Workers, durable stages, recovery, and cron-friendly CLIs
|   `-- main.py         # Application factory and ASGI app
|-- tests/              # Unit, contract, migration, DB, and deterministic E2E tests
|-- pyproject.toml      # Dependencies and tool configuration
`-- uv.lock             # Reproducible dependency lock
```
