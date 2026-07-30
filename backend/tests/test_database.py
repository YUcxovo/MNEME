"""Tests for database infrastructure that do not require a live PostgreSQL server."""

import asyncio
import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.db.session import Database, normalize_database_url
from mneme.models import Base


@pytest.mark.base
@pytest.mark.db
@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "postgresql+asyncpg://user:pass@localhost/mneme",
            "postgresql+asyncpg://user:pass@localhost/mneme",
        ),
        (
            "postgresql://user:pass@localhost/mneme",
            "postgresql+asyncpg://user:pass@localhost/mneme",
        ),
        (
            "postgres://user:pass@localhost/mneme",
            "postgresql+asyncpg://user:pass@localhost/mneme",
        ),
    ],
)
def test_normalize_database_url(source: str, expected: str) -> None:
    assert normalize_database_url(source) == expected


@pytest.mark.base
@pytest.mark.db
def test_reject_non_postgresql_url() -> None:
    with pytest.raises(ValueError, match="must be a PostgreSQL URL"):
        normalize_database_url("sqlite+aiosqlite:///mneme.db")


@pytest.mark.base
@pytest.mark.db
def test_database_builds_async_sessions_without_connecting() -> None:
    database = Database("postgresql://user:pass@localhost/mneme")

    session = database.session_factory()

    assert isinstance(session, AsyncSession)
    assert database.engine.dialect.name == "postgresql"
    assert Base.metadata.naming_convention is not None

    asyncio.run(session.close())
    asyncio.run(database.dispose())


@pytest.mark.db
def test_database_connects_when_ci_url_is_configured() -> None:
    database_url = os.getenv("MNEME_DATABASE_URL")
    if database_url is None:
        pytest.skip("MNEME_DATABASE_URL is not configured for an integration test")
    assert database_url is not None

    async def assert_connection() -> None:
        database = Database(database_url)
        try:
            await database.ping()
        finally:
            await database.dispose()

    asyncio.run(assert_connection())
