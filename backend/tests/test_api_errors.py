"""Tests for request context validation and the shared API error envelope."""

import asyncio
from typing import Annotated
from uuid import UUID

import pytest
from fastapi import FastAPI, Query, Request, status
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.exc import SQLAlchemyError

from mneme.api.errors import ApiError, ErrorResponse
from mneme.core.config import Environment, Settings
from mneme.main import create_app


def create_error_test_app(*, debug: bool = False) -> FastAPI:
    """Build an application with test-only routes that exercise each handler."""
    application = create_app(Settings(environment=Environment.TESTING, debug=debug, _env_file=None))

    @application.get("/request-context")
    async def request_context(request: Request) -> dict[str, str]:
        return {"request_id": request.state.request_id}

    @application.get("/expected-error")
    async def expected_error() -> None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "example_conflict",
            "The example conflicts with existing state.",
            details={"field": "example"},
        )

    @application.get("/validated")
    async def validated(number: Annotated[int, Query(ge=1)]) -> dict[str, int]:
        return {"number": number}

    @application.get("/unexpected-error")
    async def unexpected_error() -> None:
        raise RuntimeError("sensitive internal database detail")

    @application.get("/database-error")
    async def database_error() -> None:
        raise SQLAlchemyError("sensitive connection diagnostics")

    return application


async def request_test_route(
    path: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    raise_app_exceptions: bool = True,
    debug: bool = False,
) -> Response:
    """Issue one in-process request and release application-owned resources."""
    application = create_error_test_app(debug=debug)
    transport = ASGITransport(
        app=application,
        raise_app_exceptions=raise_app_exceptions,
    )
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path, headers=headers, params=params)
    await application.state.redis.aclose()
    await application.state.database.dispose()
    return response


@pytest.mark.base
@pytest.mark.api
def test_safe_request_id_is_available_on_request_state() -> None:
    response = asyncio.run(
        request_test_route(
            "/request-context",
            headers={"X-Request-ID": "trace-42.test"},
        )
    )

    assert response.status_code == 200
    assert response.json() == {"request_id": "trace-42.test"}
    assert response.headers["X-Request-ID"] == "trace-42.test"


@pytest.mark.base
@pytest.mark.api
def test_unsafe_request_id_is_replaced() -> None:
    response = asyncio.run(
        request_test_route(
            "/request-context",
            headers={"X-Request-ID": "x" * 129},
        )
    )

    generated_id = response.headers["X-Request-ID"]
    assert generated_id != "x" * 129
    assert response.json() == {"request_id": generated_id}
    assert str(UUID(generated_id)) == generated_id


@pytest.mark.base
@pytest.mark.api
def test_expected_api_error_uses_shared_envelope() -> None:
    response = asyncio.run(
        request_test_route(
            "/expected-error",
            headers={"X-Request-ID": "expected-1"},
        )
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "example_conflict",
        "message": "The example conflicts with existing state.",
        "request_id": "expected-1",
        "details": {"field": "example"},
    }


@pytest.mark.base
@pytest.mark.api
def test_validation_error_omits_rejected_input() -> None:
    rejected_value = "do-not-reflect-this-value"
    response = asyncio.run(
        request_test_route(
            "/validated",
            params={"number": rejected_value},
        )
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.json()["details"]["errors"][0]["location"] == ["query", "number"]
    assert rejected_value not in response.text


@pytest.mark.base
@pytest.mark.api
def test_framework_http_error_omits_raw_detail() -> None:
    response = asyncio.run(request_test_route("/route-that-does-not-exist"))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert response.json()["message"] == "Not Found"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.base
@pytest.mark.api
def test_unexpected_error_is_generic_and_keeps_request_id() -> None:
    response = asyncio.run(
        request_test_route(
            "/unexpected-error",
            headers={"X-Request-ID": "unexpected-1"},
            raise_app_exceptions=False,
            debug=True,
        )
    )

    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_error",
        "message": "An unexpected error occurred.",
        "request_id": "unexpected-1",
    }
    assert response.headers["X-Request-ID"] == "unexpected-1"
    assert "sensitive internal database detail" not in response.text


@pytest.mark.base
@pytest.mark.api
def test_database_error_is_service_unavailable_without_diagnostics() -> None:
    response = asyncio.run(
        request_test_route(
            "/database-error",
            headers={"X-Request-ID": "database-1"},
        )
    )

    assert response.status_code == 503
    assert response.json() == {
        "code": "service_unavailable",
        "message": "A required service is temporarily unavailable.",
        "request_id": "database-1",
    }
    assert "sensitive connection diagnostics" not in response.text


@pytest.mark.base
@pytest.mark.api
def test_optional_error_details_are_non_nullable_in_public_schema() -> None:
    schema = ErrorResponse.model_json_schema()
    details_schema = schema["properties"]["details"]

    assert details_schema["type"] == "object"
    assert "anyOf" not in details_schema
    assert "details" not in schema["required"]
