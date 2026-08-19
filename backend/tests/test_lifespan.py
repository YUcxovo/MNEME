"""Application resource-lifecycle tests."""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from redis.asyncio import Redis

from mneme.core.config import Environment, Settings
from mneme.db import Database
from mneme.main import create_lifespan


@pytest.mark.base
def test_lifespan_closes_lazily_created_queue_pool() -> None:
    events: list[str] = []
    database = MagicMock(spec=Database)
    database.dispose = AsyncMock(side_effect=lambda: events.append("database"))
    redis_client = MagicMock(spec=Redis)
    redis_client.aclose = AsyncMock(side_effect=lambda: events.append("redis"))
    arq_pool = MagicMock()
    arq_pool.aclose = AsyncMock(side_effect=lambda: events.append("arq"))
    application = FastAPI()
    application.state.arq_pool = arq_pool
    lifespan = create_lifespan(
        Settings(environment=Environment.TESTING, _env_file=None),
        cast(Database, database),
        cast(Redis, redis_client),
    )

    async def exercise() -> None:
        async with lifespan(application):
            pass

    asyncio.run(exercise())

    assert events == ["arq", "redis", "database"]
