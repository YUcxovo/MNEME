"""Tests for database infrastructure that do not require a live PostgreSQL server."""

import asyncio
import os
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from mneme.core.config import Environment, Settings
from mneme.db import session as session_module
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


@pytest.mark.base
@pytest.mark.db
def test_database_from_settings_applies_bounded_pool_configuration(monkeypatch) -> None:
    engine = MagicMock(spec=AsyncEngine)
    create_engine = MagicMock(return_value=engine)
    session_factory = MagicMock()
    monkeypatch.setattr(session_module, "create_async_engine", create_engine)
    monkeypatch.setattr(session_module, "async_sessionmaker", session_factory)
    settings = Settings(
        environment=Environment.TESTING,
        debug=True,
        database_url="postgresql://user:pass@database/mneme",
        database_pool_size=7,
        database_max_overflow=2,
        database_pool_timeout_seconds=8.5,
        database_pool_recycle_seconds=600,
        _env_file=None,
    )

    database = Database.from_settings(settings)

    assert database.engine is engine
    create_engine.assert_called_once_with(
        "postgresql+asyncpg://user:pass@database/mneme",
        echo=True,
        pool_pre_ping=True,
        pool_size=7,
        max_overflow=2,
        pool_timeout=8.5,
        pool_recycle=600,
    )
    session_factory.assert_called_once_with(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


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
