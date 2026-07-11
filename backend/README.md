# Mneme Backend

Minimal FastAPI scaffold for Mneme. Business logic, persistence, authentication, and
external-service integrations are intentionally added in later atomic changes.

## Requirements

- Python 3.11-3.13 (the repository selects Python 3.12)
- uv

## Setup

```bash
cd backend
uv sync --locked --dev
```

## Run

```bash
uv run uvicorn mneme.main:app --reload
```

The initial health endpoint is available at `GET http://127.0.0.1:8000/v1/health`.

Copy `.env.example` to `.env` for local overrides. All settings use the `MNEME_` prefix.
Development logs are human-readable; testing and production environments emit JSON logs.
HTTP responses include an `X-Request-ID` header for correlation.

`MNEME_DATABASE_URL` must be a PostgreSQL URL. Both `postgresql://` (used by CI) and
`postgresql+asyncpg://` are accepted. Creating the application does not connect to the
database; connections are opened lazily and disposed during FastAPI shutdown.

`MNEME_REDIS_URL` configures the shared Redis service used by caching and background-job
infrastructure. The application creates one lazy async client and connection pool, shares
it through FastAPI dependencies, and closes it during shutdown. Creating the application
does not require a running Redis server.

Run the standalone ARQ worker with:

```bash
uv run arq mneme.tasks.worker.WorkerSettings
```

The worker scaffold registers only `worker_probe`; pipeline jobs are added as separate
atomic changes. ARQ also writes its liveness state to `mneme:worker:health` every 30 seconds.

## Database migrations

Alembic uses the same `MNEME_DATABASE_URL` as the application. Create and review a
migration after changing persisted models, then apply it with:

```bash
uv run alembic revision --autogenerate -m "describe the schema change"
uv run alembic upgrade head
```

Use `uv run alembic downgrade -1` to revert the latest revision during development.
The scaffold intentionally contains no initial revision or business tables.

## Checks

```bash
uv run ruff format --check .
uv run ruff check .
uv run pyrefly check .
uv run pytest -m base
```

## Layout

```text
backend/
|-- alembic/            # Async migration environment and revision files
|-- alembic.ini         # Alembic command configuration
|-- src/mneme/          # Application package
|   |-- api/            # FastAPI routers
|   |-- core/           # Settings and structured logging
|   |-- db/             # Async engine, sessions, and FastAPI dependencies
|   |-- models/         # Declarative model base (business models added later)
|   |-- redis/          # Shared async Redis client and FastAPI dependency
|   |-- tasks/          # ARQ worker configuration and background jobs
|   `-- main.py         # Application factory and ASGI app
|-- tests/              # Pytest suite
|-- pyproject.toml      # Dependencies and tool configuration
`-- uv.lock             # Reproducible dependency lock
```
