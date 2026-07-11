"""Tests for the minimal application scaffold."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient, Response

from mneme.main import create_app


async def request_health() -> Response:
    """Issue a health request through the in-process ASGI transport."""
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/v1/health")


@pytest.mark.base
@pytest.mark.api
def test_health_endpoint() -> None:
    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.base
def test_openapi_metadata() -> None:
    application = create_app()

    assert application.title == "Mneme API"
    assert application.version == "0.1.0"
