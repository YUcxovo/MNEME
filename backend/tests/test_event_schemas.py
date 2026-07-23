"""Validation tests for the frozen behavioral-event contract."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mneme.api.schemas.events import UserEvent
from mneme.models.user import UserEventType

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)


def _payload(event_type: UserEventType) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_id": uuid4(),
        "event_type": event_type,
        "occurred_at": NOW,
    }
    if event_type != UserEventType.DIGEST_DISMISSED:
        payload["paper_id"] = uuid4()
    return payload


@pytest.mark.base
@pytest.mark.api
@pytest.mark.parametrize("event_type", list(UserEventType))
def test_all_frozen_event_types_have_a_valid_scope(event_type: UserEventType) -> None:
    event = UserEvent.model_validate(_payload(event_type))

    assert event.event_type == event_type
    assert event.context == {}


@pytest.mark.base
@pytest.mark.api
@pytest.mark.parametrize(
    "payload",
    [
        {
            **_payload(UserEventType.DIGEST_DISMISSED),
            "paper_id": uuid4(),
        },
        {
            key: value
            for key, value in _payload(UserEventType.PAPER_SAVED).items()
            if key != "paper_id"
        },
        {
            **_payload(UserEventType.PAPER_SAVED),
            "duration_ms": 1000,
        },
    ],
)
def test_event_scope_rejects_ambiguous_payloads(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        UserEvent.model_validate(payload)


@pytest.mark.base
@pytest.mark.api
def test_open_duration_accepts_database_integer_range_only() -> None:
    payload = _payload(UserEventType.PAPER_OPENED)
    assert UserEvent.model_validate({**payload, "duration_ms": 0}).duration_ms == 0
    assert (
        UserEvent.model_validate({**payload, "duration_ms": 2_147_483_647}).duration_ms
        == 2_147_483_647
    )

    with pytest.raises(ValidationError):
        UserEvent.model_validate({**payload, "duration_ms": -1})
    with pytest.raises(ValidationError):
        UserEvent.model_validate({**payload, "duration_ms": 2_147_483_648})


@pytest.mark.base
@pytest.mark.api
def test_event_timestamp_must_be_timezone_aware() -> None:
    payload = _payload(UserEventType.PAPER_SAVED)
    payload["occurred_at"] = NOW.replace(tzinfo=None)

    with pytest.raises(ValidationError, match="timezone"):
        UserEvent.model_validate(payload)


@pytest.mark.base
@pytest.mark.api
def test_json_event_types_are_not_coerced() -> None:
    payload = _payload(UserEventType.PAPER_OPENED)

    with pytest.raises(ValidationError):
        UserEvent.model_validate({**payload, "occurred_at": 1_721_736_000})
    with pytest.raises(ValidationError):
        UserEvent.model_validate({**payload, "duration_ms": True})


@pytest.mark.base
@pytest.mark.api
def test_api_event_maps_to_an_independent_service_record() -> None:
    payload = {
        **_payload(UserEventType.PAPER_OPENED),
        "duration_ms": 45_000,
        "context": {"surface": "digest"},
    }
    event = UserEvent.model_validate(payload)

    record = event.to_record()
    event.context["surface"] = "changed"

    assert record.event_id == event.event_id
    assert record.duration_ms == 45_000
    assert record.context == {"surface": "digest"}
