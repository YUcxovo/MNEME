"""Deterministic contrastive profile aggregation for behavior-v2."""

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from uuid import UUID

from mneme.models.user import UserEventType
from mneme.services.behavior import BehaviorSignal
from mneme.services.behavior_v2 import (
    DEFAULT_BEHAVIOR_CONFIG,
    EXPOSURE_EVENTS,
    SECONDS_PER_DAY,
    BehaviorEvidence,
    BehaviorModelConfig,
    BehaviorProfile,
    effective_event_weight,
)


def aggregate_behavior_profile(
    signals: Iterable[BehaviorSignal],
    embeddings_by_paper: Mapping[UUID, Sequence[float]],
    *,
    now: datetime,
    config: BehaviorModelConfig = DEFAULT_BEHAVIOR_CONFIG,
) -> BehaviorProfile:
    """Build a deterministic contrastive profile from authoritative raw events."""
    if now.tzinfo is None:
        raise ValueError("Behavior timestamps must be timezone-aware.")
    history = tuple(signals)
    if any(signal.occurred_at.tzinfo is None for signal in history):
        raise ValueError("Behavior timestamps must be timezone-aware.")

    exposures = _exposures_by_paper(history, now=now, config=config)
    masses: dict[UUID, list[float]] = defaultdict(lambda: [0.0, 0.0])
    eligible_signal_count = 0
    ignored_unexposed = 0
    out_of_window = 0

    for signal in history:
        age_days = max(0.0, (now - signal.occurred_at).total_seconds() / SECONDS_PER_DAY)
        if age_days > config.window_days:
            out_of_window += 1
            continue
        if signal.paper_id is None:
            continue
        if (
            signal.event_type is UserEventType.PAPER_SKIPPED
            and config.require_negative_exposure
            and not _has_recent_exposure(signal, exposures.get(signal.paper_id, ()), config=config)
        ):
            ignored_unexposed += 1
            continue

        weight = effective_event_weight(signal, now=now, config=config)
        if weight > 0:
            masses[signal.paper_id][0] += weight
            eligible_signal_count += 1
        elif weight < 0:
            masses[signal.paper_id][1] += abs(weight)
            eligible_signal_count += 1

    supported = {
        paper_id: (
            _saturate(values[0], config.positive_saturation_scale),
            _saturate(values[1], config.negative_saturation_scale),
        )
        for paper_id, values in masses.items()
        if values[0] > 0 or values[1] > 0
    }
    dimensions: int | None = None
    positive_vectors: list[tuple[float, Sequence[float]]] = []
    negative_vectors: list[tuple[float, Sequence[float]]] = []
    embedded_papers: set[UUID] = set()
    for paper_id in sorted(supported, key=str):
        embedding = embeddings_by_paper.get(paper_id)
        if embedding is None or not embedding:
            continue
        if dimensions is None:
            dimensions = len(embedding)
        elif len(embedding) != dimensions:
            raise ValueError("Behavior embeddings must have consistent dimensions.")
        embedded_papers.add(paper_id)
        positive_support, negative_support = supported[paper_id]
        if positive_support > 0:
            positive_vectors.append((positive_support, embedding))
        if negative_support > 0:
            negative_vectors.append((negative_support, embedding))

    positive_embedding = _normalized_centroid(positive_vectors, dimensions=dimensions)
    negative_embedding = _normalized_centroid(negative_vectors, dimensions=dimensions)
    positive_support = math.fsum(weight for weight, _ in positive_vectors)
    negative_support = math.fsum(weight for weight, _ in negative_vectors)
    eligible_paper_count = len(supported)
    embedded_paper_count = len(embedded_papers)
    coverage = embedded_paper_count / eligible_paper_count if eligible_paper_count else 0.0
    confidence = (
        _confidence(
            support=positive_support + negative_support,
            diversity=embedded_paper_count,
            coverage=coverage,
            config=config,
        )
        if positive_embedding is not None or negative_embedding is not None
        else 0.0
    )
    return BehaviorProfile(
        positive_embedding=positive_embedding,
        negative_embedding=negative_embedding,
        confidence=confidence,
        evidence=BehaviorEvidence(
            signal_count=len(history),
            eligible_signal_count=eligible_signal_count,
            ignored_unexposed_negative_count=ignored_unexposed,
            out_of_window_signal_count=out_of_window,
            eligible_paper_count=eligible_paper_count,
            embedded_paper_count=embedded_paper_count,
            positive_paper_count=len(positive_vectors),
            negative_paper_count=len(negative_vectors),
            positive_support=positive_support,
            negative_support=negative_support,
            embedding_coverage=coverage,
            parameter_hash=config.parameter_hash(),
        ),
    )


def _exposures_by_paper(
    signals: Sequence[BehaviorSignal],
    *,
    now: datetime,
    config: BehaviorModelConfig,
) -> dict[UUID, tuple[datetime, ...]]:
    exposures: dict[UUID, list[datetime]] = defaultdict(list)
    for signal in signals:
        if signal.paper_id is None or signal.event_type not in EXPOSURE_EVENTS:
            continue
        age_days = max(0.0, (now - signal.occurred_at).total_seconds() / SECONDS_PER_DAY)
        if age_days <= config.window_days:
            exposures[signal.paper_id].append(signal.occurred_at)
    return {paper_id: tuple(sorted(times)) for paper_id, times in exposures.items()}


def _has_recent_exposure(
    signal: BehaviorSignal,
    exposure_times: Sequence[datetime],
    *,
    config: BehaviorModelConfig,
) -> bool:
    lookback_seconds = config.exposure_lookback_days * SECONDS_PER_DAY
    return any(
        0 <= (signal.occurred_at - exposed_at).total_seconds() <= lookback_seconds
        for exposed_at in exposure_times
    )


def _saturate(value: float, scale: float | None) -> float:
    if scale is None:
        return value
    return 1 - math.exp(-value / scale)


def _normalized_centroid(
    weighted_vectors: Sequence[tuple[float, Sequence[float]]],
    *,
    dimensions: int | None,
) -> tuple[float, ...] | None:
    if dimensions is None or not weighted_vectors:
        return None
    aggregate = tuple(
        math.fsum(weight * float(vector[index]) for weight, vector in weighted_vectors)
        for index in range(dimensions)
    )
    norm = math.sqrt(math.fsum(value * value for value in aggregate))
    if math.isclose(norm, 0.0, abs_tol=1e-12):
        return None
    return tuple(value / norm for value in aggregate)


def _confidence(
    *,
    support: float,
    diversity: int,
    coverage: float,
    config: BehaviorModelConfig,
) -> float:
    if support <= 0 or diversity <= 0 or coverage <= 0:
        return 0.0
    mass_term = 1 - math.exp(-support / config.confidence_mass_scale)
    diversity_term = 1 - math.exp(-diversity / config.confidence_diversity_scale)
    return max(0.0, min(1.0, coverage * math.sqrt(mass_term * diversity_term)))
