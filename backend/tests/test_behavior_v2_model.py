"""Pure tests for the frozen behavior-v2 profile algorithm."""

import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from mneme.models.user import UserEventType
from mneme.services.behavior import BehaviorSignal
from mneme.services.behavior_v2 import (
    BEHAVIOR_MODEL_NAME,
    BEHAVIOR_MODEL_VERSION,
    DEFAULT_BEHAVIOR_CONFIG,
    BehaviorModelConfig,
    effective_event_weight,
    open_duration_multiplier,
    temporal_decay,
)
from mneme.services.behavior_v2_profile import aggregate_behavior_profile

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
PAPER_A = UUID("00000000-0000-0000-0000-000000000001")
PAPER_B = UUID("00000000-0000-0000-0000-000000000002")
PAPER_C = UUID("00000000-0000-0000-0000-000000000003")


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
def test_default_identity_and_parameter_hash_are_stable() -> None:
    assert BEHAVIOR_MODEL_NAME == "behavior-v2"
    assert BEHAVIOR_MODEL_VERSION == 2
    assert len(DEFAULT_BEHAVIOR_CONFIG.parameter_hash()) == 64
    assert DEFAULT_BEHAVIOR_CONFIG.parameter_hash() == BehaviorModelConfig().parameter_hash()
    assert BehaviorModelConfig(short_term_mix=0.6).parameter_hash() != (
        DEFAULT_BEHAVIOR_CONFIG.parameter_hash()
    )


@pytest.mark.base
@pytest.mark.parametrize(
    ("duration_ms", "expected"),
    [
        (None, 1.0),
        (0, 0.5),
        (300_000, 1.5),
        (600_000, 1.5),
    ],
)
def test_open_duration_is_continuous_and_bounded(duration_ms: int | None, expected: float) -> None:
    assert open_duration_multiplier(duration_ms) == pytest.approx(expected)


@pytest.mark.base
def test_dual_timescale_decay_and_window() -> None:
    expected = 0.7 * 0.5 + 0.3 * (0.5 ** (14 / 60))
    assert temporal_decay(14, config=DEFAULT_BEHAVIOR_CONFIG) == pytest.approx(expected)
    assert effective_event_weight(_signal(UserEventType.PAPER_SAVED), now=NOW) == 3
    assert effective_event_weight(_signal(UserEventType.PAPER_SAVED, age_days=180.01), now=NOW) == 0


@pytest.mark.base
def test_skip_requires_recent_exposure() -> None:
    unexposed = aggregate_behavior_profile(
        [_signal(UserEventType.PAPER_SKIPPED)],
        {PAPER_A: (1.0, 0.0)},
        now=NOW,
    )
    exposed = aggregate_behavior_profile(
        [
            _signal(UserEventType.PAPER_IMPRESSION, age_days=1),
            _signal(UserEventType.PAPER_SKIPPED),
        ],
        {PAPER_A: (1.0, 0.0)},
        now=NOW,
    )

    assert unexposed.negative_embedding is None
    assert unexposed.evidence.ignored_unexposed_negative_count == 1
    assert exposed.negative_embedding == pytest.approx((1.0, 0.0))
    assert exposed.evidence.ignored_unexposed_negative_count == 0


@pytest.mark.base
def test_old_exposure_does_not_qualify_a_skip() -> None:
    profile = aggregate_behavior_profile(
        [
            _signal(UserEventType.PAPER_IMPRESSION, age_days=8),
            _signal(UserEventType.PAPER_SKIPPED),
        ],
        {PAPER_A: (1.0, 0.0)},
        now=NOW,
    )

    assert profile.negative_embedding is None
    assert profile.evidence.ignored_unexposed_negative_count == 1


@pytest.mark.base
def test_positive_and_negative_channels_do_not_cancel() -> None:
    profile = aggregate_behavior_profile(
        [
            _signal(UserEventType.PAPER_SAVED, paper_id=PAPER_A),
            _signal(UserEventType.PAPER_IMPRESSION, paper_id=PAPER_B, age_days=1),
            _signal(UserEventType.PAPER_SKIPPED, paper_id=PAPER_B),
        ],
        {PAPER_A: (1.0, 0.0), PAPER_B: (0.0, 1.0)},
        now=NOW,
    )

    assert profile.positive_embedding == pytest.approx((1.0, 0.0))
    assert profile.negative_embedding == pytest.approx((0.0, 1.0))
    assert 0 < profile.confidence < 1
    assert profile.evidence.positive_paper_count == 1
    assert profile.evidence.negative_paper_count == 1


@pytest.mark.base
def test_per_paper_saturation_rewards_diverse_evidence() -> None:
    repeated = aggregate_behavior_profile(
        [_signal(UserEventType.PAPER_OPENED) for _ in range(6)],
        {PAPER_A: (1.0, 0.0)},
        now=NOW,
    )
    diverse = aggregate_behavior_profile(
        [
            _signal(UserEventType.PAPER_OPENED, paper_id=PAPER_A),
            _signal(UserEventType.PAPER_OPENED, paper_id=PAPER_B),
            _signal(UserEventType.PAPER_OPENED, paper_id=PAPER_C),
        ],
        {
            PAPER_A: (1.0, 0.0),
            PAPER_B: (0.9, 0.1),
            PAPER_C: (0.8, 0.2),
        },
        now=NOW,
    )

    assert diverse.confidence > repeated.confidence
    assert repeated.evidence.embedded_paper_count == 1
    assert diverse.evidence.embedded_paper_count == 3


@pytest.mark.base
def test_missing_embeddings_reduce_coverage_and_confidence() -> None:
    signals = [
        _signal(UserEventType.PAPER_SAVED, paper_id=PAPER_A),
        _signal(UserEventType.PAPER_SAVED, paper_id=PAPER_B),
    ]
    complete = aggregate_behavior_profile(
        signals,
        {PAPER_A: (1.0, 0.0), PAPER_B: (0.0, 1.0)},
        now=NOW,
    )
    partial = aggregate_behavior_profile(
        signals,
        {PAPER_A: (1.0, 0.0)},
        now=NOW,
    )

    assert complete.evidence.embedding_coverage == 1.0
    assert partial.evidence.embedding_coverage == 0.5
    assert partial.confidence < complete.confidence


@pytest.mark.base
def test_replay_is_order_independent_and_has_a_golden_centroid() -> None:
    signals = [
        _signal(UserEventType.PAPER_SAVED, paper_id=PAPER_A),
        _signal(UserEventType.PAPER_OPENED, paper_id=PAPER_B, age_days=14),
    ]
    embeddings = {PAPER_A: (1.0, 0.0), PAPER_B: (0.0, 1.0)}

    forward = aggregate_behavior_profile(signals, embeddings, now=NOW)
    reverse = aggregate_behavior_profile(reversed(signals), embeddings, now=NOW)

    saved_support = 1 - math.exp(-3 / 3)
    opened_weight = temporal_decay(14, config=DEFAULT_BEHAVIOR_CONFIG)
    opened_support = 1 - math.exp(-opened_weight / 3)
    norm = math.sqrt(saved_support**2 + opened_support**2)
    assert forward == reverse
    assert forward.positive_embedding == pytest.approx(
        (saved_support / norm, opened_support / norm)
    )


@pytest.mark.base
def test_empty_history_returns_an_inspectable_zero_confidence_profile() -> None:
    profile = aggregate_behavior_profile([], {}, now=NOW)

    assert profile.positive_embedding is None
    assert profile.negative_embedding is None
    assert profile.confidence == 0
    assert profile.evidence.signal_count == 0
    assert profile.evidence.embedding_coverage == 0


@pytest.mark.base
def test_cancelled_channels_cannot_retain_actionable_confidence() -> None:
    profile = aggregate_behavior_profile(
        [
            _signal(UserEventType.PAPER_SAVED, paper_id=PAPER_A),
            _signal(UserEventType.PAPER_SAVED, paper_id=PAPER_B),
        ],
        {PAPER_A: (1.0, 0.0), PAPER_B: (-1.0, 0.0)},
        now=NOW,
    )

    assert profile.positive_embedding is None
    assert profile.negative_embedding is None
    assert profile.confidence == 0


@pytest.mark.base
def test_invalid_timestamps_dimensions_and_configuration_fail_closed() -> None:
    naive = BehaviorSignal(
        event_type=UserEventType.PAPER_SAVED,
        paper_id=PAPER_A,
        occurred_at=NOW.replace(tzinfo=None),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        aggregate_behavior_profile([naive], {PAPER_A: (1.0, 0.0)}, now=NOW)
    with pytest.raises(ValueError, match="consistent dimensions"):
        aggregate_behavior_profile(
            [
                _signal(UserEventType.PAPER_SAVED, paper_id=PAPER_A),
                _signal(UserEventType.PAPER_SAVED, paper_id=PAPER_B),
            ],
            {PAPER_A: (1.0, 0.0), PAPER_B: (1.0,)},
            now=NOW,
        )
    with pytest.raises(ValueError, match="long half-life"):
        BehaviorModelConfig(short_half_life_days=60, long_half_life_days=14)


@pytest.mark.base
def test_ablation_can_disable_negative_exposure_gate() -> None:
    profile = aggregate_behavior_profile(
        [_signal(UserEventType.PAPER_SKIPPED)],
        {PAPER_A: (1.0, 0.0)},
        now=NOW,
        config=BehaviorModelConfig(require_negative_exposure=False),
    )

    assert profile.negative_embedding == pytest.approx((1.0, 0.0))
    assert profile.evidence.ignored_unexposed_negative_count == 0
