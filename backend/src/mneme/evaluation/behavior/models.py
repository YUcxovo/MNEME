"""Frozen model registry and result schemas for controlled evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from mneme.ai.recommendation import BehaviorScoringConfig
from mneme.evaluation.behavior.fixtures import ScenarioFamily, ScenarioPhase
from mneme.services.behavior_v2 import DEFAULT_BEHAVIOR_CONFIG, BehaviorModelConfig


@dataclass(frozen=True, slots=True)
class BehaviorEvaluationModel:
    """One headline model or mechanism ablation."""

    model_id: str
    behavior_kind: Literal["none", "v1", "v2"]
    include_explicit_topics: bool
    headline: bool
    behavior_config: BehaviorModelConfig | None = None
    scoring_config: BehaviorScoringConfig = field(default_factory=BehaviorScoringConfig)

    def configuration_payload(self) -> dict[str, object]:
        """Return complete, JSON-compatible model provenance."""
        return {
            "behavior_config": (
                self.behavior_config.canonical_payload()
                if self.behavior_config is not None
                else None
            ),
            "behavior_kind": self.behavior_kind,
            "headline": self.headline,
            "include_explicit_topics": self.include_explicit_topics,
            "model_id": self.model_id,
            "scoring_config": asdict(self.scoring_config),
        }


def evaluation_models() -> tuple[BehaviorEvaluationModel, ...]:
    """Return the protocol-frozen headline systems and v2 ablations."""
    models = (
        BehaviorEvaluationModel(
            model_id="recency-only",
            behavior_kind="none",
            include_explicit_topics=False,
            headline=True,
        ),
        BehaviorEvaluationModel(
            model_id="explicit-recency",
            behavior_kind="none",
            include_explicit_topics=True,
            headline=True,
        ),
        BehaviorEvaluationModel(
            model_id="behavior-v1",
            behavior_kind="v1",
            include_explicit_topics=True,
            headline=True,
        ),
        BehaviorEvaluationModel(
            model_id="behavior-v2",
            behavior_kind="v2",
            include_explicit_topics=True,
            headline=True,
            behavior_config=DEFAULT_BEHAVIOR_CONFIG,
        ),
        BehaviorEvaluationModel(
            model_id="v2-single-timescale",
            behavior_kind="v2",
            include_explicit_topics=True,
            headline=False,
            behavior_config=replace(
                DEFAULT_BEHAVIOR_CONFIG,
                short_half_life_days=30.0,
                short_term_mix=1.0,
            ),
        ),
        BehaviorEvaluationModel(
            model_id="v2-no-saturation",
            behavior_kind="v2",
            include_explicit_topics=True,
            headline=False,
            behavior_config=replace(
                DEFAULT_BEHAVIOR_CONFIG,
                positive_saturation_scale=None,
                negative_saturation_scale=None,
            ),
        ),
        BehaviorEvaluationModel(
            model_id="v2-no-exposure-gate",
            behavior_kind="v2",
            include_explicit_topics=True,
            headline=False,
            behavior_config=replace(
                DEFAULT_BEHAVIOR_CONFIG,
                require_negative_exposure=False,
            ),
        ),
        BehaviorEvaluationModel(
            model_id="v2-no-negative-channel",
            behavior_kind="v2",
            include_explicit_topics=True,
            headline=False,
            behavior_config=DEFAULT_BEHAVIOR_CONFIG,
            scoring_config=BehaviorScoringConfig(use_negative_channel=False),
        ),
        BehaviorEvaluationModel(
            model_id="v2-no-confidence-gate",
            behavior_kind="v2",
            include_explicit_topics=True,
            headline=False,
            behavior_config=DEFAULT_BEHAVIOR_CONFIG,
            scoring_config=BehaviorScoringConfig(use_confidence_gate=False),
        ),
    )
    if len({model.model_id for model in models}) != len(models):
        raise RuntimeError("Behavior evaluation model IDs must be unique.")
    return models


class RankedCandidateResult(BaseModel):
    """One fully ranked controlled candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    paper_id: UUID
    rank: int = Field(ge=1)
    score: float = Field(ge=0, le=1)
    reasons: tuple[str, ...] = Field(min_length=1)


class CaseMetrics(BaseModel):
    """Ranking and target metrics for one case-model combination."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ndcg_at_k: float | None = Field(default=None, ge=0, le=1)
    recall_at_k: float | None = Field(default=None, ge=0, le=1)
    reciprocal_rank: float | None = Field(default=None, ge=0, le=1)
    intra_list_diversity_at_k: float | None = Field(default=None, ge=0, le=1)
    target_rank: int | None = Field(default=None, ge=1)
    target_score: float | None = Field(default=None, ge=0, le=1)


class InvariantResults(BaseModel):
    """Exact software and mechanism checks recorded with a case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finite_scores: bool
    bounded_scores: bool
    deterministic_replay: bool
    stable_tie_break: bool
    exposure_gate: bool | None = None
    duplicate_idempotency: bool | None = None


class BehaviorCaseResult(BaseModel):
    """Machine-readable result for one scenario and one model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["behavior-case-result-v1"] = "behavior-case-result-v1"
    scenario_id: str
    scenario_family: ScenarioFamily
    pair_id: str | None
    phase: ScenarioPhase
    model_id: str
    model_version: int | None
    parameter_hash: str | None
    input_event_count: int
    unique_event_count: int
    profile_confidence: float | None = Field(default=None, ge=0, le=1)
    embedding_coverage: float | None = Field(default=None, ge=0, le=1)
    ranking: tuple[RankedCandidateResult, ...]
    metrics: CaseMetrics
    invariants: InvariantResults
