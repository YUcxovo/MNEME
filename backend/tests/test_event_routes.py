"""Contract tests for behavioral-event ingestion."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.dependencies.events import get_behavior_event_service
from mneme.api.errors import register_error_handlers
from mneme.api.middleware import request_context_middleware
from mneme.api.routes.events import router as events_router
from mneme.repositories.events import EventRecord
from mneme.services.events import (
    EventIngestionStats,
    EventPaperNotFoundError,
    EventUserNotFoundError,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000111")
PAPER_ID = UUID("00000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)


class FakeEventService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[UUID, list[EventRecord]]] = []

    async def ingest(self, user_id: UUID, events: list[EventRecord]) -> EventIngestionStats:
        self.calls.append((user_id, events))
        if self.error is not None:
            raise self.error
        return EventIngestionStats(accepted=len(events), duplicates=0)


def _application(service: FakeEventService) -> FastAPI:
    async def principal_override() -> Principal:
        return Principal(user_id=USER_ID)

    async def service_override() -> FakeEventService:
        return service

    application = FastAPI()
    application.middleware("http")(request_context_middleware)
    register_error_handlers(application)
    application.include_router(events_router, prefix="/v1")
    application.dependency_overrides[require_principal] = principal_override
    application.dependency_overrides[get_behavior_event_service] = service_override
    return application


async def _post(application: FastAPI, payload: object) -> Response:
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/v1/events",
            json=payload,
            headers={"X-Request-ID": "event-test"},
        )


def _payload() -> dict[str, object]:
    return {
        "event_id": str(uuid4()),
        "event_type": "paper_opened",
        "paper_id": str(PAPER_ID),
        "occurred_at": NOW.isoformat(),
        "duration_ms": 45_000,
        "context": {"surface": "digest"},
    }


@pytest.mark.base
@pytest.mark.api
def test_event_endpoint_accepts_raw_array_and_maps_records() -> None:
    service = FakeEventService()

    response = asyncio.run(_post(_application(service), [_payload()]))

    assert response.status_code == 200
    assert response.json() == {"accepted": 1, "duplicates": 0}
    user_id, records = service.calls[0]
    assert user_id == USER_ID
    assert records[0].paper_id == PAPER_ID
    assert records[0].duration_ms == 45_000
    assert records[0].context == {"surface": "digest"}


@pytest.mark.base
@pytest.mark.api
@pytest.mark.parametrize(
    ("error", "code", "message"),
    [
        (
            EventUserNotFoundError(),
            "user_not_found",
            "The authenticated user does not exist.",
        ),
        (
            EventPaperNotFoundError(),
            "paper_not_found",
            "One or more referenced papers do not exist.",
        ),
    ],
)
def test_event_endpoint_maps_expected_lookup_errors(
    error: Exception,
    code: str,
    message: str,
) -> None:
    response = asyncio.run(_post(_application(FakeEventService(error)), [_payload()]))

    assert response.status_code == 404
    assert response.json() == {
        "code": code,
        "message": message,
        "request_id": "event-test",
    }


@pytest.mark.base
@pytest.mark.api
def test_event_endpoint_accepts_empty_and_five_hundred_item_batches() -> None:
    empty_service = FakeEventService()
    full_service = FakeEventService()
    full_batch = [
        {
            "event_id": str(uuid4()),
            "event_type": "digest_dismissed",
            "occurred_at": NOW.isoformat(),
        }
        for _ in range(500)
    ]

    empty = asyncio.run(_post(_application(empty_service), []))
    full = asyncio.run(_post(_application(full_service), full_batch))

    assert empty.json() == {"accepted": 0, "duplicates": 0}
    assert full.json() == {"accepted": 500, "duplicates": 0}


@pytest.mark.base
@pytest.mark.api
def test_event_endpoint_rejects_batches_above_contract_limit() -> None:
    service = FakeEventService()
    payload = [
        {
            "event_id": str(uuid4()),
            "event_type": "digest_dismissed",
            "occurred_at": NOW.isoformat(),
        }
        for _ in range(501)
    ]

    response = asyncio.run(_post(_application(service), payload))

    assert response.status_code == 422
    assert service.calls == []


@pytest.mark.base
@pytest.mark.api
def test_event_openapi_matches_frozen_contract() -> None:
    schema = _application(FakeEventService()).openapi()
    operation = schema["paths"]["/v1/events"]["post"]
    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]

    assert operation["operationId"] == "ingestEvents"
    assert operation["security"] == [{"demoToken": []}]
    assert request_schema["type"] == "array"
    assert request_schema["maxItems"] == 500
    assert request_schema["items"] == {"$ref": "#/components/schemas/UserEvent"}
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/EventIngestionResult"
    }
