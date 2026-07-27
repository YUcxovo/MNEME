"""Versioned parameters and event weighting for behavior-v2."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Final

from mneme.models.user import UserEventType
from mneme.services.behavior import BehaviorSignal

BEHAVIOR_MODEL_NAME: Final = "behavior-v2"
BEHAVIOR_MODEL_VERSION: Final = 2

SECONDS_PER_DAY: Final = 86_400
EVENT_WEIGHTS: Final[dict[UserEventType, float]] = {
    UserEventType.PAPER_IMPRESSION: 0.0,
    UserEventType.PAPER_OPENED: 1.0,
    UserEventType.PAPER_SAVED: 3.0,
    UserEventType.PAPER_SKIPPED: -1.0,
    UserEventType.PAPER_SHARED: 4.0,
    UserEventType.QUESTION_ASKED: 2.0,
    UserEventType.DIGEST_DISMISSED: 0.0,
}
EXPOSURE_EVENTS: Final = frozenset({UserEventType.PAPER_IMPRESSION, UserEventType.PAPER_OPENED})


@dataclass(frozen=True, slots=True)
class BehaviorModelConfig:
    """Frozen parameters for one replayable behavior-v2 variant."""

    short_half_life_days: float = 14.0
    long_half_life_days: float = 60.0
    short_term_mix: float = 0.70
    window_days: float = 180.0
    exposure_lookback_days: float = 7.0
    positive_saturation_scale: float | None = 3.0
    negative_saturation_scale: float | None = 1.0
    confidence_mass_scale: float = 3.0
    confidence_diversity_scale: float = 3.0
    require_negative_exposure: bool = True

    def __post_init__(self) -> None:
        positive_values = (
            self.short_half_life_days,
            self.long_half_life_days,
            self.window_days,
            self.exposure_lookback_days,
            self.confidence_mass_scale,
            self.confidence_diversity_scale,
        )
        if any(value <= 0 for value in positive_values):
            raise ValueError("Behavior-v2 time and confidence scales must be positive.")
        if self.long_half_life_days <= self.short_half_life_days:
            raise ValueError("The long half-life must exceed the short half-life.")
        if not 0 <= self.short_term_mix <= 1:
            raise ValueError("The short-term mixture weight must be in [0, 1].")
        for scale in (self.positive_saturation_scale, self.negative_saturation_scale):
            if scale is not None and scale <= 0:
                raise ValueError("Behavior-v2 saturation scales must be positive or null.")

    def canonical_payload(self) -> dict[str, float | bool | None]:
        """Return a stable JSON-compatible parameter representation."""
        return asdict(self)

    def parameter_hash(self) -> str:
        """Return the SHA-256 identity of the complete parameter set."""
        encoded = json.dumps(
            self.canonical_payload(), separators=(",", ":"), sort_keys=True
        ).encode("ascii")
        return hashlib.sha256(encoded).hexdigest()


DEFAULT_BEHAVIOR_CONFIG: Final = BehaviorModelConfig()


@dataclass(frozen=True, slots=True)
class BehaviorEvidence:
    """Inspectable evidence summary retained with a derived profile."""

    signal_count: int
    eligible_signal_count: int
    ignored_unexposed_negative_count: int
    out_of_window_signal_count: int
    eligible_paper_count: int
    embedded_paper_count: int
    positive_paper_count: int
    negative_paper_count: int
    positive_support: float
    negative_support: float
    embedding_coverage: float
    parameter_hash: str

    def as_json(self) -> dict[str, int | float | str]:
        """Return fields suitable for the preference JSONB column."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BehaviorProfile:
    """Positive and negative interest channels plus bounded confidence."""

    positive_embedding: tuple[float, ...] | None
    negative_embedding: tuple[float, ...] | None
    confidence: float
    evidence: BehaviorEvidence
    model_name: str = BEHAVIOR_MODEL_NAME
    model_version: int = BEHAVIOR_MODEL_VERSION


def open_duration_multiplier(duration_ms: int | None) -> float:
    """Map observed reading duration continuously into the bounded [0.5, 1.5] range."""
    if duration_ms is None:
        return 1.0
    seconds = min(max(duration_ms, 0) / 1_000, 300.0)
    return 0.5 + math.log1p(seconds / 30.0) / math.log(11.0)


def temporal_decay(age_days: float, *, config: BehaviorModelConfig) -> float:
    """Return the fixed mixture of recent and persistent exponential decay."""
    bounded_age = max(0.0, age_days)
    short = 0.5 ** (bounded_age / config.short_half_life_days)
    long = 0.5 ** (bounded_age / config.long_half_life_days)
    return config.short_term_mix * short + (1 - config.short_term_mix) * long


def effective_event_weight(
    signal: BehaviorSignal,
    *,
    now: datetime,
    config: BehaviorModelConfig = DEFAULT_BEHAVIOR_CONFIG,
) -> float:
    """Return signed duration-adjusted and dual-timescale-decayed evidence."""
    if now.tzinfo is None or signal.occurred_at.tzinfo is None:
        raise ValueError("Behavior timestamps must be timezone-aware.")
    age_days = max(0.0, (now - signal.occurred_at).total_seconds() / SECONDS_PER_DAY)
    if age_days > config.window_days:
        return 0.0
    duration = (
        open_duration_multiplier(signal.duration_ms)
        if signal.event_type is UserEventType.PAPER_OPENED
        else 1.0
    )
    return EVENT_WEIGHTS[signal.event_type] * duration * temporal_decay(age_days, config=config)
