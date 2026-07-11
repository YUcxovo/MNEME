"""Tests for the minimal application scaffold."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient, Response
from redis.asyncio import Redis

from mneme.core.config import Environment, Settings
from mneme.main import create_app


async def request_health(request_id: str | None = None) -> Response:
    """Issue a health request through the in-process ASGI transport."""
    settings = Settings(environment=Environment.TESTING, _env_file=None)
    transport = ASGITransport(app=create_app(settings))
    headers = {"X-Request-ID": request_id} if request_id else None
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/v1/health", headers=headers)


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
def test_openapi_metadata() -> None:
    application = create_app()

    assert application.title == "Mneme API"
    assert application.version == "0.1.0"
    assert application.state.database.engine.dialect.name == "postgresql"
    assert isinstance(application.state.redis, Redis)

    asyncio.run(application.state.redis.aclose())
    asyncio.run(application.state.database.dispose())
