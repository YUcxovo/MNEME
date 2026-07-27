"""Controlled tests for the environment-sensitive behavior performance benchmark."""

import pytest

from mneme.evaluation.behavior.performance import run_behavior_performance_benchmark
from mneme.evaluation.behavior.performance_models import (
    DEFAULT_BEHAVIOR_PERFORMANCE_CONFIG,
    BehaviorPerformanceConfig,
    PerformanceScale,
)

pytestmark = pytest.mark.base


def _tiny_config() -> BehaviorPerformanceConfig:
    return BehaviorPerformanceConfig(
        embedding_dimensions=8,
        warmup_repetitions=1,
        measured_repetitions=2,
        top_k=2,
        seed=17,
        scales=(PerformanceScale("tiny", 12, 3, 5),),
    )


def test_default_performance_protocol_is_frozen() -> None:
    config = DEFAULT_BEHAVIOR_PERFORMANCE_CONFIG

    assert config.embedding_dimensions == 1536
    assert config.warmup_repetitions == 5
    assert config.measured_repetitions == 30
    assert config.top_k == 20
    assert config.seed == 20260727
    assert config.scales == (
        PerformanceScale("small", 64, 16, 50),
        PerformanceScale("medium", 512, 128, 200),
        PerformanceScale("large", 4096, 512, 1000),
    )


def test_performance_config_rejects_invalid_counts_and_duplicate_scales() -> None:
    with pytest.raises(ValueError, match="counts must be positive"):
        BehaviorPerformanceConfig(measured_repetitions=0)
    with pytest.raises(ValueError, match="scale IDs must be unique"):
        BehaviorPerformanceConfig(
            scales=(
                PerformanceScale("same", 1, 1, 1),
                PerformanceScale("same", 2, 2, 2),
            )
        )
    with pytest.raises(ValueError, match="scale sizes must be positive"):
        BehaviorPerformanceConfig(scales=(PerformanceScale("bad", 0, 1, 1),))


def test_tiny_benchmark_retains_raw_samples_and_descriptive_summaries() -> None:
    result = run_behavior_performance_benchmark(_tiny_config())

    assert result.schema_version == "behavior-performance-v1"
    assert result.environment_sensitive is True
    assert result.measured_repetitions == 2
    assert len(result.cases) == 1
    case = result.cases[0]
    assert case.scale_id == "tiny"
    assert case.embedding_dimensions == 8
    assert 0 < case.profile_confidence <= 1
    assert len(case.ranking_checksum) == 64
    for timing in (case.aggregation, case.ranking):
        assert len(timing.samples_ms) == 2
        assert timing.minimum_ms <= timing.median_ms <= timing.maximum_ms
        assert timing.minimum_ms <= timing.p95_ms <= timing.maximum_ms
        assert timing.median_throughput_per_second > 0


def test_repeated_benchmarks_preserve_semantic_outputs() -> None:
    first = run_behavior_performance_benchmark(_tiny_config()).cases[0]
    second = run_behavior_performance_benchmark(_tiny_config()).cases[0]

    assert first.profile_confidence == second.profile_confidence
    assert first.ranking_checksum == second.ranking_checksum
