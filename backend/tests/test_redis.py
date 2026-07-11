"""Tests for application-scoped Redis infrastructure."""

import asyncio
from typing import cast

import pytest
from fastapi import Request
from redis.asyncio import Redis
from starlette.types import Scope

from mneme.core.config import Settings
from mneme.main import create_app
from mneme.redis import create_redis_client
from mneme.redis.dependencies import get_redis


@pytest.mark.base
def test_redis_client_uses_configured_pool_without_connecting() -> None:
    settings = Settings(
        redis_url="redis://cache:6380/2",
        redis_max_connections=7,
        redis_socket_timeout_seconds=3,
        _env_file=None,
    )

    client = create_redis_client(settings)
    connection_kwargs = client.connection_pool.connection_kwargs

    assert isinstance(client, Redis)
    assert connection_kwargs["host"] == "cache"
    assert connection_kwargs["port"] == 6380
    assert connection_kwargs["db"] == 2
    assert client.connection_pool.max_connections == 7
    assert connection_kwargs["decode_responses"] is True
    assert connection_kwargs["socket_connect_timeout"] == 3
    assert connection_kwargs["socket_timeout"] == 3

    asyncio.run(client.aclose())


@pytest.mark.base
def test_redis_dependency_returns_application_client() -> None:
    application = create_app(Settings(_env_file=None))
    request = Request(cast(Scope, {"type": "http", "app": application}))

    assert get_redis(request) is application.state.redis

    asyncio.run(application.state.redis.aclose())
    asyncio.run(application.state.database.dispose())
