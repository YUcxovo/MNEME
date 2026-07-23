"""Deterministic behavior-v1 preference aggregation."""

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from mneme.models.user import UserEventType

BEHAVIOR_MODEL_NAME: Final = "behavior-v1"
BEHAVIOR_MODEL_VERSION: Final = 1
BEHAVIOR_HALF_LIFE_DAYS: Final = 30.0
BEHAVIOR_WINDOW_DAYS: Final = 90.0

_EVENT_WEIGHTS: Final[dict[UserEventType, float]] = {
    UserEventType.PAPER_IMPRESSION: 0.1,
    UserEventType.PAPER_OPENED: 1.0,
    UserEventType.PAPER_SAVED: 3.0,
    UserEventType.PAPER_SKIPPED: -1.0,
    UserEventType.PAPER_SHARED: 4.0,
    UserEventType.QUESTION_ASKED: 2.0,
    UserEventType.DIGEST_DISMISSED: 0.0,
}


@dataclass(frozen=True, slots=True)
class BehaviorSignal:
    """The event fields needed by the pure aggregation algorithm."""

    event_type: UserEventType
    paper_id: UUID | None
    occurred_at: datetime
    duration_ms: int | None = None


def effective_event_weight(signal: BehaviorSignal, *, now: datetime) -> float:
    """Return the duration-adjusted and time-decayed signed signal weight."""
    if now.tzinfo is None or signal.occurred_at.tzinfo is None:
        raise ValueError("Behavior timestamps must be timezone-aware.")

    age_days = max(0.0, (now - signal.occurred_at).total_seconds() / 86_400)
    if age_days > BEHAVIOR_WINDOW_DAYS:
        return 0.0

    duration_multiplier = 1.0
    if signal.event_type == UserEventType.PAPER_OPENED and signal.duration_ms is not None:
        if signal.duration_ms < 30_000:
            duration_multiplier = 0.5
        elif signal.duration_ms > 180_000:
            duration_multiplier = 1.5

    decay = 0.5 ** (age_days / BEHAVIOR_HALF_LIFE_DAYS)
    return _EVENT_WEIGHTS[signal.event_type] * duration_multiplier * decay


def aggregate_behavior_embedding(
    signals: Iterable[BehaviorSignal],
    embeddings_by_paper: Mapping[UUID, Sequence[float]],
    *,
    now: datetime,
) -> tuple[float, ...] | None:
    """Return the signed, absolute-weight normalized, L2-normalized aggregate."""
    weighted_vectors: list[tuple[float, Sequence[float]]] = []
    dimensions: int | None = None
    for signal in signals:
        if signal.paper_id is None:
            continue
        embedding = embeddings_by_paper.get(signal.paper_id)
        weight = effective_event_weight(signal, now=now)
        if embedding is None or not embedding or weight == 0:
            continue
        if dimensions is None:
            dimensions = len(embedding)
        if len(embedding) != dimensions:
            raise ValueError("Behavior embeddings must have consistent dimensions.")
        weighted_vectors.append((weight, embedding))

    if dimensions is None or not weighted_vectors:
        return None

    denominator = math.fsum(abs(weight) for weight, _ in weighted_vectors)
    if denominator == 0:
        return None
    aggregate = tuple(
        math.fsum(weight * float(embedding[index]) for weight, embedding in weighted_vectors)
        / denominator
        for index in range(dimensions)
    )
    norm = math.sqrt(math.fsum(value * value for value in aggregate))
    if math.isclose(norm, 0.0, abs_tol=1e-12):
        return None
    return tuple(value / norm for value in aggregate)
