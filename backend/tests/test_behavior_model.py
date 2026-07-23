"""Pure tests for the frozen behavior-v1 aggregation rules."""

import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from mneme.models.user import UserEventType
from mneme.services.behavior import (
    BehaviorSignal,
    aggregate_behavior_embedding,
    effective_event_weight,
)

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
PAPER_A = UUID("00000000-0000-0000-0000-000000000001")
PAPER_B = UUID("00000000-0000-0000-0000-000000000002")


def _signal(
    event_type: UserEventType,
    *,
    paper_id: UUID | None = PAPER_A,
    age_days: float = 0,
    duration_ms: int | None = None,
) -> BehaviorSignal:
    return BehaviorSignal(
        event_type=event_type,
        paper_id=paper_id,
        occurred_at=NOW - timedelta(days=age_days),
        duration_ms=duration_ms,
    )


@pytest.mark.base
@pytest.mark.parametrize(
    ("event_type", "expected"),
    [
        (UserEventType.PAPER_IMPRESSION, 0.1),
        (UserEventType.PAPER_OPENED, 1.0),
        (UserEventType.PAPER_SAVED, 3.0),
        (UserEventType.PAPER_SKIPPED, -1.0),
        (UserEventType.PAPER_SHARED, 4.0),
        (UserEventType.QUESTION_ASKED, 2.0),
        (UserEventType.DIGEST_DISMISSED, 0.0),
    ],
)
def test_behavior_v1_base_weights(event_type: UserEventType, expected: float) -> None:
    assert effective_event_weight(_signal(event_type), now=NOW) == expected


@pytest.mark.base
@pytest.mark.parametrize(
    ("duration_ms", "expected"),
    [
        (None, 1.0),
        (0, 0.5),
        (29_999, 0.5),
        (30_000, 1.0),
        (180_000, 1.0),
        (180_001, 1.5),
    ],
)
def test_open_duration_thresholds(duration_ms: int | None, expected: float) -> None:
    signal = _signal(UserEventType.PAPER_OPENED, duration_ms=duration_ms)

    assert effective_event_weight(signal, now=NOW) == expected


@pytest.mark.base
def test_behavior_weight_has_thirty_day_half_life_and_ninety_day_window() -> None:
    signal = _signal(UserEventType.PAPER_SAVED, age_days=30)
    expired = _signal(UserEventType.PAPER_SAVED, age_days=90.01)

    assert effective_event_weight(signal, now=NOW) == pytest.approx(1.5)
    assert effective_event_weight(expired, now=NOW) == 0


@pytest.mark.base
def test_future_device_timestamp_is_clamped_to_zero_age() -> None:
    signal = BehaviorSignal(
        event_type=UserEventType.PAPER_SAVED,
        paper_id=PAPER_A,
        occurred_at=NOW + timedelta(minutes=5),
    )

    assert effective_event_weight(signal, now=NOW) == 3


@pytest.mark.base
def test_aggregate_preserves_signed_feedback_and_decay() -> None:
    signals = [
        _signal(UserEventType.PAPER_SAVED, paper_id=PAPER_A),
        _signal(UserEventType.PAPER_SKIPPED, paper_id=PAPER_B, age_days=30),
    ]

    result = aggregate_behavior_embedding(
        signals,
        {PAPER_A: (1.0, 0.0), PAPER_B: (0.0, 1.0)},
        now=NOW,
    )

    assert result is not None
    norm = math.sqrt(3.0**2 + 0.5**2)
    assert result == pytest.approx((3.0 / norm, -0.5 / norm))


@pytest.mark.base
def test_empty_missing_and_cancelled_signals_produce_no_vector() -> None:
    opened = _signal(UserEventType.PAPER_OPENED)
    skipped = _signal(UserEventType.PAPER_SKIPPED)

    assert aggregate_behavior_embedding([], {}, now=NOW) is None
    assert aggregate_behavior_embedding([opened], {}, now=NOW) is None
    assert (
        aggregate_behavior_embedding(
            [opened, skipped],
            {PAPER_A: (1.0, 0.0)},
            now=NOW,
        )
        is None
    )


@pytest.mark.base
def test_aggregation_rejects_naive_timestamps_and_dimension_mismatch() -> None:
    naive = BehaviorSignal(
        event_type=UserEventType.PAPER_SAVED,
        paper_id=PAPER_A,
        occurred_at=NOW.replace(tzinfo=None),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        aggregate_behavior_embedding([naive], {PAPER_A: (1.0, 0.0)}, now=NOW)

    with pytest.raises(ValueError, match="consistent dimensions"):
        aggregate_behavior_embedding(
            [
                _signal(UserEventType.PAPER_SAVED, paper_id=PAPER_A),
                _signal(UserEventType.PAPER_SAVED, paper_id=PAPER_B),
            ],
            {PAPER_A: (1.0, 0.0), PAPER_B: (1.0,)},
            now=NOW,
        )
