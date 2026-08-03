"""HTTP boundary tests for demo preparation."""

import asyncio
import json

import httpx
import pytest

from mneme.demo.client import DemoSeedClient, DemoSeedRemoteError


@pytest.mark.base
def test_demo_seed_client_sends_bearer_token_without_exposing_it() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer raw-secret-token"
        return httpx.Response(503, json={"detail": "raw-secret-token"})

    http = httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(handler)
    )
    client = DemoSeedClient(
        base_url="http://127.0.0.1:8000",
        token="raw-secret-token",
        timeout_seconds=30,
        client=http,
    )

    with pytest.raises(DemoSeedRemoteError) as captured:
        asyncio.run(client.initialize("1706.03762"))

    assert captured.value.operation == "onboarding"
    assert captured.value.status_code == 503
    assert "raw-secret-token" not in str(captured.value)
    asyncio.run(client.aclose())


@pytest.mark.base
def test_demo_seed_client_rejects_invalid_success_json() -> None:
    http = httpx.AsyncClient(
        base_url="http://127.0.0.1:8000",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=b"not-json")),
    )
    client = DemoSeedClient(
        base_url="http://127.0.0.1:8000",
        token="token",
        timeout_seconds=30,
        client=http,
    )

    with pytest.raises(DemoSeedRemoteError):
        asyncio.run(client.initialize("1706.03762"))
    asyncio.run(client.aclose())


@pytest.mark.base
def test_demo_seed_remote_error_has_no_response_body() -> None:
    error = DemoSeedRemoteError("events", 422)
    assert json.dumps(error.__dict__, sort_keys=True) == (
        '{"operation": "events", "status_code": 422}'
    )
