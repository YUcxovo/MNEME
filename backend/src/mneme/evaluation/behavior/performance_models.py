"""Frozen configuration and artifact models for behavior performance evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True, slots=True)
class PerformanceScale:
    """One frozen workload size for the environment-sensitive benchmark."""

    scale_id: str
    signal_count: int
    history_paper_count: int
    candidate_count: int


@dataclass(frozen=True, slots=True)
class BehaviorPerformanceConfig:
    """Complete benchmark configuration fixed before recorded measurement."""

    embedding_dimensions: int = 1536
    warmup_repetitions: int = 5
    measured_repetitions: int = 30
    top_k: int = 20
    seed: int = 20260727
    scales: tuple[PerformanceScale, ...] = (
        PerformanceScale("small", 64, 16, 50),
        PerformanceScale("medium", 512, 128, 200),
        PerformanceScale("large", 4096, 512, 1000),
    )

    def __post_init__(self) -> None:
        positive = (
            self.embedding_dimensions,
            self.warmup_repetitions,
            self.measured_repetitions,
            self.top_k,
        )
        if any(value < 1 for value in positive):
            raise ValueError("Behavior performance counts must be positive.")
        if not self.scales:
            raise ValueError("Behavior performance requires at least one scale.")
        if len({scale.scale_id for scale in self.scales}) != len(self.scales):
            raise ValueError("Behavior performance scale IDs must be unique.")
        for scale in self.scales:
            if min(scale.signal_count, scale.history_paper_count, scale.candidate_count) < 1:
                raise ValueError("Behavior performance scale sizes must be positive.")


DEFAULT_BEHAVIOR_PERFORMANCE_CONFIG = BehaviorPerformanceConfig()


class TimingSummary(BaseModel):
    """Raw timing samples and descriptive summaries for one operation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    samples_ms: tuple[float, ...] = Field(min_length=1)
    median_ms: float = Field(ge=0)
    p95_ms: float = Field(ge=0)
    minimum_ms: float = Field(ge=0)
    maximum_ms: float = Field(ge=0)
    median_throughput_per_second: float = Field(ge=0)


class PerformanceCaseResult(BaseModel):
    """Performance result for one workload scale."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scale_id: str
    signal_count: int = Field(ge=1)
    history_paper_count: int = Field(ge=1)
    candidate_count: int = Field(ge=1)
    embedding_dimensions: int = Field(ge=1)
    profile_confidence: float = Field(ge=0, le=1)
    ranking_checksum: str
    aggregation: TimingSummary
    ranking: TimingSummary


class BehaviorPerformanceResult(BaseModel):
    """Complete benchmark result without machine or source provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["behavior-performance-v1"] = "behavior-performance-v1"
    environment_sensitive: Literal[True] = True
    seed: int
    warmup_repetitions: int = Field(ge=1)
    measured_repetitions: int = Field(ge=1)
    top_k: int = Field(ge=1)
    cases: tuple[PerformanceCaseResult, ...] = Field(min_length=1)
