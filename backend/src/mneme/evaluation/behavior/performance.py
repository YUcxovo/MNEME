"""Environment-sensitive performance benchmark for behavior-v2 production paths."""

from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter_ns
from typing import TypeVar
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel

from mneme.ai.recommendation import PaperCandidate, PreferenceView, rank_candidates
from mneme.evaluation.behavior.performance_models import (
    DEFAULT_BEHAVIOR_PERFORMANCE_CONFIG,
    BehaviorPerformanceConfig,
    BehaviorPerformanceResult,
    PerformanceCaseResult,
    PerformanceScale,
    TimingSummary,
)
from mneme.models.user import UserEventType
from mneme.services.behavior import BehaviorSignal
from mneme.services.behavior_v2_profile import aggregate_behavior_profile

ResultT = TypeVar("ResultT")


@dataclass(frozen=True, slots=True)
class _GeneratedCase:
    signals: tuple[BehaviorSignal, ...]
    embeddings: dict[UUID, tuple[float, ...]]
    candidates: list[PaperCandidate]
    now: datetime


def run_behavior_performance_benchmark(
    config: BehaviorPerformanceConfig = DEFAULT_BEHAVIOR_PERFORMANCE_CONFIG,
) -> BehaviorPerformanceResult:
    """Measure production aggregation and ranking over deterministic generated inputs."""
    cases = tuple(
        _benchmark_scale(scale, config=config, scale_index=index)
        for index, scale in enumerate(config.scales)
    )
    return BehaviorPerformanceResult(
        seed=config.seed,
        warmup_repetitions=config.warmup_repetitions,
        measured_repetitions=config.measured_repetitions,
        top_k=config.top_k,
        cases=cases,
    )


def _benchmark_scale(
    scale: PerformanceScale,
    *,
    config: BehaviorPerformanceConfig,
    scale_index: int,
) -> PerformanceCaseResult:
    generated = _generate_case(scale, config=config, scale_index=scale_index)
    profile = aggregate_behavior_profile(
        generated.signals,
        generated.embeddings,
        now=generated.now,
    )
    preferences = PreferenceView(
        behavior_embedding=profile.positive_embedding,
        negative_behavior_embedding=profile.negative_embedding,
        behavior_confidence=profile.confidence,
        model_version=profile.model_version,
    )
    expected_ranking = rank_candidates(
        generated.candidates,
        preferences,
        now=generated.now,
        limit=config.top_k,
    )
    aggregation = _time_operation(
        lambda: aggregate_behavior_profile(
            generated.signals,
            generated.embeddings,
            now=generated.now,
        ),
        expected=profile,
        work_items=scale.signal_count,
        config=config,
    )
    ranking = _time_operation(
        lambda: rank_candidates(
            generated.candidates,
            preferences,
            now=generated.now,
            limit=config.top_k,
        ),
        expected=expected_ranking,
        work_items=scale.candidate_count,
        config=config,
    )
    return PerformanceCaseResult(
        scale_id=scale.scale_id,
        signal_count=scale.signal_count,
        history_paper_count=scale.history_paper_count,
        candidate_count=scale.candidate_count,
        embedding_dimensions=config.embedding_dimensions,
        profile_confidence=profile.confidence,
        ranking_checksum=_ranking_checksum(expected_ranking),
        aggregation=aggregation,
        ranking=ranking,
    )


def _time_operation(
    operation: Callable[[], ResultT],
    *,
    expected: ResultT,
    work_items: int,
    config: BehaviorPerformanceConfig,
) -> TimingSummary:
    for _ in range(config.warmup_repetitions):
        if operation() != expected:
            raise RuntimeError("Behavior performance warm-up changed deterministic output.")
    samples: list[float] = []
    for _ in range(config.measured_repetitions):
        started = perf_counter_ns()
        result = operation()
        elapsed_ms = (perf_counter_ns() - started) / 1_000_000
        if result != expected:
            raise RuntimeError("Behavior performance measurement changed deterministic output.")
        samples.append(round(elapsed_ms, 6))
    median_ms = statistics.median(samples)
    return TimingSummary(
        samples_ms=tuple(samples),
        median_ms=round(median_ms, 6),
        p95_ms=round(_percentile(samples, 0.95), 6),
        minimum_ms=min(samples),
        maximum_ms=max(samples),
        median_throughput_per_second=round(work_items / (median_ms / 1000), 2),
    )


def _generate_case(
    scale: PerformanceScale,
    *,
    config: BehaviorPerformanceConfig,
    scale_index: int,
) -> _GeneratedCase:
    now = datetime(2026, 7, 27, 12, tzinfo=UTC)
    history_ids = tuple(
        uuid5(NAMESPACE_URL, f"mneme:{scale.scale_id}:history:{index}")
        for index in range(scale.history_paper_count)
    )
    embeddings = {
        paper_id: _unit_embedding(
            config.embedding_dimensions,
            seed=config.seed + scale_index * 1_000_000 + index,
        )
        for index, paper_id in enumerate(history_ids)
    }
    event_cycle = (
        UserEventType.PAPER_IMPRESSION,
        UserEventType.PAPER_OPENED,
        UserEventType.PAPER_SAVED,
        UserEventType.QUESTION_ASKED,
        UserEventType.PAPER_SHARED,
        UserEventType.PAPER_SKIPPED,
    )
    signals = tuple(
        BehaviorSignal(
            event_type=event_cycle[(index // scale.history_paper_count) % len(event_cycle)],
            paper_id=history_ids[index % scale.history_paper_count],
            occurred_at=now - timedelta(minutes=scale.signal_count - index),
            duration_ms=(index % 300 + 1) * 1000,
        )
        for index in range(scale.signal_count)
    )
    candidates = [
        PaperCandidate(
            paper_id=uuid5(NAMESPACE_URL, f"mneme:{scale.scale_id}:candidate:{index}"),
            title=f"Controlled candidate {index}",
            categories=("cs.AI",),
            published_at=now - timedelta(hours=index % 72),
            embedding=_unit_embedding(
                config.embedding_dimensions,
                seed=config.seed + scale_index * 1_000_000 + 100_000 + index,
            ),
        )
        for index in range(scale.candidate_count)
    ]
    return _GeneratedCase(
        signals=signals,
        embeddings=embeddings,
        candidates=candidates,
        now=now,
    )


def _unit_embedding(dimensions: int, *, seed: int) -> tuple[float, ...]:
    random_source = random.Random(seed)
    vector = tuple(random_source.uniform(-1.0, 1.0) for _ in range(dimensions))
    norm = math.sqrt(math.fsum(value * value for value in vector))
    return tuple(value / norm for value in vector)


def _percentile(values: Sequence[float], proportion: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * proportion
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _ranking_checksum(ranking: Sequence[BaseModel]) -> str:
    payload = [item.model_dump(mode="json") for item in ranking]
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()
