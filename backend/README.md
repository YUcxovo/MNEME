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
|-- src/mneme/          # Application package
|   |-- api/            # FastAPI routers
|   |-- core/           # Settings and structured logging
|   |-- db/             # Async engine, sessions, and FastAPI dependencies
|   |-- models/         # Declarative model base (business models added later)
|   `-- main.py         # Application factory and ASGI app
|-- tests/              # Pytest suite
|-- pyproject.toml      # Dependencies and tool configuration
`-- uv.lock             # Reproducible dependency lock
```
