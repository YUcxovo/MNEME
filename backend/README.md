# Mneme Backend

FastAPI backend for the Mneme research assistant. Milestone 1 provides a real arXiv
metadata-to-API path, the frozen v0.1 persistence model, and the shared platform boundary
for later PDF, behavior, graph, and AI work.

## Requirements

- Python 3.11-3.13 (the repository currently selects Python 3.12)
- uv
- PostgreSQL 16 with the pgvector extension
- Redis only when running ARQ or exercising Redis-backed features

## Setup

```bash
cd backend
uv sync --locked --dev
cp .env.example .env
uv run alembic upgrade head
```

All settings use the `MNEME_` prefix. `MNEME_DATABASE_URL` accepts both
`postgresql://` and `postgresql+asyncpg://` URLs. Application construction is lazy and
does not itself connect to PostgreSQL or Redis.

Protected endpoints require a pre-provisioned user UUID and only the SHA-256 digest of an
opaque token. Keep the raw token outside git and the production Android source. To configure
the local demo identity:

1. Choose a strong raw token and retain it in a local secret store.
2. Run `uv run python -m mneme.cli.hash_demo_token`, enter the token at the hidden prompt,
   and set the printed digest as `MNEME_DEMO_TOKEN_SHA256` in `.env`.
3. Generate a UUID, set it as `MNEME_DEMO_USER_ID`, then provision its rows:

```bash
uv run python -c "import uuid; print(uuid.uuid4())"
uv run python -m mneme.cli.bootstrap_demo_user
```

The bootstrap command is idempotent and never overwrites existing preferences or handles
the raw token.

## Ingest and run

Fetch and atomically persist one newest-first arXiv category page:

```bash
uv run python -m mneme.cli.fetch_arxiv cs.AI --max-results 20
```

The client identifies Mneme, serializes requests, waits at least three seconds between
attempts, honors `Retry-After`, and retries only transient transport/status failures. The
command stores metadata and every observed revision; it does not migrate the database,
download PDFs, or enqueue later pipeline stages.

Start the API:

```bash
uv run uvicorn mneme.main:app --reload
```

Available Milestone 1 routes are:

- `GET /v1/health` (public process liveness)
- `GET /v1/papers` (authenticated keyset page)
- `GET /v1/papers/{paper_id}` (authenticated detail)
- `GET /v1/users/me/preferences` (authenticated explicit preferences)
- `PUT /v1/users/me/preferences` (authenticated full replacement)
- `GET /v1/papers/{paper_id}/summary` (authenticated; deterministic abstract-derived
  placeholder in Milestone 1, real generation arrives in Milestone 2)

For example:

```bash
curl -H "Authorization: Bearer <raw-token>" http://127.0.0.1:8000/v1/papers
```

Responses include `X-Request-ID`. Errors use the stable `ErrorResponse` shape and do not
return raw validation inputs, secrets, database diagnostics, or tracebacks.

Run the standalone ARQ worker with:

```bash
uv run arq mneme.tasks.worker.WorkerSettings
```

The current worker registers only `worker_probe`; staged PDF/AI jobs arrive in later
milestones.

## AI services

All LLM access goes through `mneme.ai` (see `docs/architecture/ai-services.md`): a
provider abstraction over the Anthropic and OpenAI SDKs, task-to-model routing, a Redis
completion cache, and a hard daily budget (`MNEME_AI_DAILY_BUDGET_USD`). Configure at
least one of `MNEME_ANTHROPIC_API_KEY` / `MNEME_OPENAI_API_KEY` for live generation;
the Milestone 1 mock summary endpoint works without keys. The evaluation fixture format
and seed cases are documented in `docs/architecture/ai-evaluation.md`.

## Database migrations

Alembic uses `MNEME_DATABASE_URL`. The initial revision creates the v0.1 tables and enables
pgvector before creating vector columns.

```bash
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
```

After a model change, create and review a separate revision rather than editing an applied
migration:

```bash
uv run alembic revision --autogenerate -m "describe the schema change"
```

## Checks

```bash
uv run ruff format --check .
uv run ruff check .
uv run pyrefly check .
uv run pytest -m base
uv run pytest
```

Database integration tests run when `MNEME_DATABASE_URL` is configured. CI supplies a
PostgreSQL 16 pgvector service automatically.

## Current limitations

- Authentication is a single-user demo mechanism; there is no login, JWT, or token lifecycle.
- The arXiv command ingests one page on demand; daily scheduling belongs to Milestone 2.
- Metadata starts in `metadata_only`; PDF parsing, chunking, embeddings, and real LLM
  summaries are not part of this milestone. `GET /v1/papers/{paper_id}/summary` serves a
  deterministic placeholder derived from the stored abstract.
- `GET /v1/health` does not probe PostgreSQL or Redis.
- The committed full v0.1 contract remains authoritative for later routes; FastAPI currently
  generates and verifies the implemented Milestone 1 subset.

## Layout

```text
backend/
|-- alembic/            # Async migration environment and versioned revisions
|-- src/mneme/
|   |-- ai/             # LLM providers, routing, budget, cache, evaluation harness
|   |-- api/            # Routers, dependencies, schemas, middleware, shared errors
|   |-- cli/            # Demo bootstrap/token tools and arXiv ingestion command
|   |-- core/           # Settings, logging, and security helpers
|   |-- db/             # Async engine, sessions, and FastAPI dependencies
|   |-- models/         # SQLAlchemy v0.1 persistence model
|   |-- repositories/   # Transaction and query boundaries
|   |-- services/       # External clients and ingestion orchestration
|   |-- redis/          # Shared Redis client and dependencies
|   |-- tasks/          # ARQ worker configuration
|   `-- main.py         # Application factory and ASGI app
|-- tests/              # Unit, contract, migration, and gated DB integration tests
|-- pyproject.toml      # Dependencies and tool configuration
`-- uv.lock             # Reproducible dependency lock
```
