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
|   `-- main.py         # Application factory and ASGI app
|-- tests/              # Pytest suite
|-- pyproject.toml      # Dependencies and tool configuration
`-- uv.lock             # Reproducible dependency lock
```
