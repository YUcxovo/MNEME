"""Tests for the pre-provisioned opaque demo-token dependency."""

import asyncio
from typing import Annotated
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient, Response

from mneme.api.dependencies.auth import Principal, require_principal
from mneme.core.config import Environment, Settings
from mneme.core.security import token_matches_sha256, token_sha256
from mneme.main import create_app

DEMO_TOKEN = "local-test-token"
DEMO_USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def create_protected_app(*, configured: bool = True) -> FastAPI:
    """Build an application with one test-only protected endpoint."""
    settings = Settings(
        environment=Environment.TESTING,
        demo_token_sha256=token_sha256(DEMO_TOKEN) if configured else None,
        demo_user_id=DEMO_USER_ID if configured else None,
        _env_file=None,
    )
    application = create_app(settings)

    @application.get("/v1/protected")
    async def protected(
        principal: Annotated[Principal, Depends(require_principal)],
    ) -> dict[str, str]:
        return {"user_id": str(principal.user_id)}

    return application


async def request_protected(
    *,
    configured: bool = True,
    authorization: str | None = None,
) -> Response:
    """Issue one protected request without opening external service connections."""
    application = create_protected_app(configured=configured)
    transport = ASGITransport(app=application)
    headers = {"Authorization": authorization} if authorization is not None else None
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/protected", headers=headers)
    await application.state.redis.aclose()
    await application.state.database.dispose()
    return response


@pytest.mark.base
@pytest.mark.api
def test_valid_demo_token_returns_typed_principal() -> None:
    response = asyncio.run(request_protected(authorization=f"Bearer {DEMO_TOKEN}"))

    assert response.status_code == 200
    assert response.json() == {"user_id": str(DEMO_USER_ID)}


@pytest.mark.base
@pytest.mark.api
@pytest.mark.parametrize("authorization", [None, "Basic dXNlcjpwYXNz"])
def test_missing_or_malformed_bearer_token_is_deterministic(
    authorization: str | None,
) -> None:
    response = asyncio.run(request_protected(authorization=authorization))

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"
    assert response.json()["message"] == "A Bearer token is required."
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.base
@pytest.mark.api
def test_invalid_demo_token_does_not_leak_credentials() -> None:
    invalid_token = "do-not-return-this-token"
    response = asyncio.run(request_protected(authorization=f"Bearer {invalid_token}"))

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"
    assert invalid_token not in response.text
    assert DEMO_TOKEN not in response.text


@pytest.mark.base
@pytest.mark.api
def test_missing_authentication_configuration_is_service_unavailable() -> None:
    response = asyncio.run(
        request_protected(
            configured=False,
            authorization=f"Bearer {DEMO_TOKEN}",
        )
    )

    assert response.status_code == 503
    assert response.json()["code"] == "service_unavailable"
    assert response.json()["message"] == "Authentication is not configured."


@pytest.mark.base
@pytest.mark.api
def test_generated_openapi_declares_opaque_bearer_scheme() -> None:
    application = create_protected_app()
    schema = application.openapi()

    scheme = schema["components"]["securitySchemes"]["demoToken"]
    assert scheme["type"] == "http"
    assert scheme["scheme"] == "bearer"
    assert scheme["bearerFormat"] == "opaque-demo-token"
    assert schema["paths"]["/v1/protected"]["get"]["security"] == [{"demoToken": []}]
    assert "security" not in schema["paths"]["/v1/health"]["get"]

    asyncio.run(application.state.redis.aclose())
    asyncio.run(application.state.database.dispose())


@pytest.mark.base
def test_token_sha256_matches_case_insensitive_hex_digest() -> None:
    digest = token_sha256(DEMO_TOKEN)

    assert len(digest) == 64
    assert token_matches_sha256(DEMO_TOKEN, digest.upper()) is True
    assert token_matches_sha256("different", digest) is False
