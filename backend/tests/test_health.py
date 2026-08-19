"""Tests for the minimal application scaffold."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient, Response
from redis.asyncio import Redis

from mneme.api.routes.health import (
    ReadinessDependencies,
    get_readiness_dependencies,
)
from mneme.core.config import Environment, Settings
from mneme.main import create_app


async def request_health(request_id: str | None = None) -> Response:
    """Issue a health request through the in-process ASGI transport."""
    settings = Settings(environment=Environment.TESTING, _env_file=None)
    transport = ASGITransport(app=create_app(settings))
    headers = {"X-Request-ID": request_id} if request_id else None
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/v1/health", headers=headers)


async def request_readiness(dependencies: ReadinessDependencies) -> Response:
    application = create_app(Settings(environment=Environment.TESTING, _env_file=None))

    async def override_dependencies() -> ReadinessDependencies:
        return dependencies

    application.dependency_overrides[get_readiness_dependencies] = override_dependencies
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/health/ready", headers={"X-Request-ID": "ready-1"})
    await application.state.redis.aclose()
    await application.state.database.dispose()
    return response


@pytest.mark.base
@pytest.mark.api
def test_health_endpoint() -> None:
    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


@pytest.mark.base
@pytest.mark.api
def test_request_id_is_preserved() -> None:
    response = asyncio.run(request_health("test-request-id"))

    assert response.headers["X-Request-ID"] == "test-request-id"


@pytest.mark.base
@pytest.mark.api
def test_liveness_does_not_resolve_readiness_dependencies() -> None:
    application = create_app(Settings(environment=Environment.TESTING, _env_file=None))

    async def fail_if_called() -> ReadinessDependencies:
        raise AssertionError("liveness must not probe dependencies")

    application.dependency_overrides[get_readiness_dependencies] = fail_if_called

    async def request() -> Response:
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/v1/health")

    response = asyncio.run(request())
    assert response.status_code == 200

    asyncio.run(application.state.redis.aclose())
    asyncio.run(application.state.database.dispose())


@pytest.mark.base
@pytest.mark.api
def test_readiness_returns_dependency_statuses() -> None:
    response = asyncio.run(
        request_readiness(ReadinessDependencies(postgresql="ready", redis="ready"))
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dependencies": {"postgresql": "ready", "redis": "ready"},
    }


@pytest.mark.base
@pytest.mark.api
def test_readiness_failure_is_safe_and_correlated() -> None:
    response = asyncio.run(
        request_readiness(ReadinessDependencies(postgresql="unavailable", redis="ready"))
    )

    assert response.status_code == 503
    assert response.json() == {
        "code": "service_unavailable",
        "message": "A required service is temporarily unavailable.",
        "request_id": "ready-1",
        "details": {"dependencies": {"postgresql": "unavailable", "redis": "ready"}},
    }


@pytest.mark.base
@pytest.mark.api
def test_readiness_probes_are_bounded_and_independent() -> None:
    database = MagicMock()
    database.ping = AsyncMock()
    redis = MagicMock()
    redis.ping = AsyncMock(side_effect=ConnectionError("sensitive Redis URL"))
    settings = Settings(readiness_timeout_seconds=0.05, _env_file=None)

    dependencies = asyncio.run(get_readiness_dependencies(database, redis, settings))

    assert dependencies == ReadinessDependencies(postgresql="ready", redis="unavailable")
    database.ping.assert_awaited_once()
    redis.ping.assert_awaited_once()


@pytest.mark.base
@pytest.mark.api
def test_readiness_probe_times_out() -> None:
    async def block() -> None:
        await asyncio.sleep(1)

    database = MagicMock()
    database.ping = AsyncMock(side_effect=block)
    redis = MagicMock()
    redis.ping = AsyncMock(return_value=True)
    settings = Settings(readiness_timeout_seconds=0.01, _env_file=None)

    dependencies = asyncio.run(get_readiness_dependencies(database, redis, settings))

    assert dependencies == ReadinessDependencies(postgresql="unavailable", redis="ready")


@pytest.mark.base
def test_openapi_metadata() -> None:
    application = create_app()

    assert application.title == "Mneme API"
    assert application.version == "0.1.0"
    assert application.state.database.engine.dialect.name == "postgresql"
    assert isinstance(application.state.redis, Redis)

    asyncio.run(application.state.redis.aclose())
    asyncio.run(application.state.database.dispose())
