"""Deterministic controlled replay through production behavior and ranking code."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

from mneme.ai.recommendation import PreferenceView, ScoredPaper, rank_candidates
from mneme.evaluation.behavior.fixtures import (
    BehaviorFixtureFile,
    BehaviorScenario,
    ScenarioFamily,
    scenario_candidates,
    scenario_embeddings,
    scenario_signals,
)
from mneme.evaluation.behavior.metrics import (
    intra_list_diversity,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)
from mneme.evaluation.behavior.models import (
    BehaviorCaseResult,
    BehaviorEvaluationModel,
    CaseMetrics,
    InvariantResults,
    RankedCandidateResult,
    evaluation_models,
)
from mneme.services.behavior import BEHAVIOR_MODEL_VERSION as V1_MODEL_VERSION
from mneme.services.behavior import aggregate_behavior_embedding
from mneme.services.behavior_v2 import BEHAVIOR_MODEL_VERSION as V2_MODEL_VERSION
from mneme.services.behavior_v2_profile import aggregate_behavior_profile


@dataclass(frozen=True, slots=True)
class _EvaluationState:
    preferences: PreferenceView
    scored: tuple[ScoredPaper, ...]
    model_version: int | None
    parameter_hash: str | None
    profile_confidence: float | None
    embedding_coverage: float | None
    exposure_gate: bool | None


def evaluate_scenario(
    scenario: BehaviorScenario,
    *,
    fixture: BehaviorFixtureFile,
    model: BehaviorEvaluationModel,
) -> BehaviorCaseResult:
    """Evaluate one case twice and retain exact replay invariants."""
    first = _evaluate_once(scenario, fixture=fixture, model=model)
    second = _evaluate_once(scenario, fixture=fixture, model=model)
    ranking = tuple(
        RankedCandidateResult(
            paper_id=item.paper_id,
            rank=rank,
            score=item.score,
            reasons=item.reasons,
        )
        for rank, item in enumerate(first.scored, 1)
    )
    ranked_ids = [item.paper_id for item in first.scored]
    judgments = {item.paper_id: item for item in scenario.judgments}
    k = fixture.evaluation.metric_k
    target = next(
        (item for item in ranking if item.paper_id == scenario.target_paper_id),
        None,
    )
    scores = [item.score for item in first.scored]
    return BehaviorCaseResult(
        scenario_id=scenario.scenario_id,
        scenario_family=scenario.family,
        pair_id=scenario.pair_id,
        phase=scenario.phase,
        model_id=model.model_id,
        model_version=first.model_version,
        parameter_hash=first.parameter_hash,
        input_event_count=len(scenario.events),
        unique_event_count=len({event.event_id for event in scenario.events}),
        profile_confidence=first.profile_confidence,
        embedding_coverage=first.embedding_coverage,
        ranking=ranking,
        metrics=CaseMetrics(
            ndcg_at_k=ndcg_at_k(ranked_ids, judgments, k=k),
            recall_at_k=recall_at_k(ranked_ids, judgments, k=k),
            reciprocal_rank=reciprocal_rank(ranked_ids, judgments),
            intra_list_diversity_at_k=intra_list_diversity(
                ranked_ids,
                scenario_embeddings(fixture),
                k=k,
            ),
            target_rank=target.rank if target is not None else None,
            target_score=target.score if target is not None else None,
        ),
        invariants=InvariantResults(
            finite_scores=all(math.isfinite(score) for score in scores),
            bounded_scores=all(0 <= score <= 1 for score in scores),
            deterministic_replay=first == second,
            stable_tie_break=_has_stable_tie_break(first.scored),
            exposure_gate=first.exposure_gate,
        ),
    )


def run_behavior_evaluation(
    fixture: BehaviorFixtureFile,
    *,
    models: tuple[BehaviorEvaluationModel, ...] | None = None,
) -> tuple[BehaviorCaseResult, ...]:
    """Run every declared scenario-model pair without external dependencies."""
    selected_models = models or evaluation_models()
    cases = tuple(
        evaluate_scenario(scenario, fixture=fixture, model=model)
        for scenario in fixture.scenarios
        for model in selected_models
    )
    return _annotate_duplicate_replay(cases)


def _evaluate_once(
    scenario: BehaviorScenario,
    *,
    fixture: BehaviorFixtureFile,
    model: BehaviorEvaluationModel,
) -> _EvaluationState:
    signals = scenario_signals(scenario)
    embeddings = scenario_embeddings(fixture)
    explicit_topics = scenario.explicit_topics if model.include_explicit_topics else ()
    parameter_hash: str | None = None
    confidence: float | None = None
    coverage: float | None = None
    exposure_gate: bool | None = None

    if model.behavior_kind == "v1":
        preferences = PreferenceView(
            explicit_topics=explicit_topics,
            behavior_embedding=aggregate_behavior_embedding(
                signals,
                embeddings,
                now=fixture.reference_time_utc,
            ),
            model_version=V1_MODEL_VERSION,
        )
        model_version: int | None = V1_MODEL_VERSION
    elif model.behavior_kind == "v2":
        if model.behavior_config is None:
            raise ValueError("Behavior-v2 evaluation models require a complete configuration.")
        profile = aggregate_behavior_profile(
            signals,
            embeddings,
            now=fixture.reference_time_utc,
            config=model.behavior_config,
        )
        preferences = PreferenceView(
            explicit_topics=explicit_topics,
            behavior_embedding=profile.positive_embedding,
            negative_behavior_embedding=profile.negative_embedding,
            behavior_confidence=profile.confidence,
            model_version=V2_MODEL_VERSION,
        )
        model_version = V2_MODEL_VERSION
        parameter_hash = model.behavior_config.parameter_hash()
        confidence = profile.confidence
        coverage = profile.evidence.embedding_coverage
        if scenario.family is ScenarioFamily.UNEXPOSED_SKIP:
            exposure_gate = profile.evidence.ignored_unexposed_negative_count > 0
    else:
        preferences = PreferenceView(explicit_topics=explicit_topics)
        model_version = None

    scored = tuple(
        rank_candidates(
            scenario_candidates(fixture, scenario),
            preferences,
            now=fixture.reference_time_utc,
            limit=len(scenario.candidate_ids),
            behavior_config=model.scoring_config,
        )
    )
    return _EvaluationState(
        preferences=preferences,
        scored=scored,
        model_version=model_version,
        parameter_hash=parameter_hash,
        profile_confidence=confidence,
        embedding_coverage=coverage,
        exposure_gate=exposure_gate,
    )


def _has_stable_tie_break(scored: tuple[ScoredPaper, ...]) -> bool:
    return all(
        previous.score != current.score or str(previous.paper_id) < str(current.paper_id)
        for previous, current in pairwise(scored)
    )


def _annotate_duplicate_replay(
    cases: tuple[BehaviorCaseResult, ...],
) -> tuple[BehaviorCaseResult, ...]:
    grouped: dict[tuple[str, str], list[BehaviorCaseResult]] = {}
    for case in cases:
        if case.scenario_family is ScenarioFamily.DUPLICATE_REPLAY and case.pair_id is not None:
            grouped.setdefault((case.pair_id, case.model_id), []).append(case)

    annotated: list[BehaviorCaseResult] = []
    for case in cases:
        group = grouped.get((case.pair_id or "", case.model_id))
        if group is None:
            annotated.append(case)
            continue
        identical = len(group) == 2 and group[0].ranking == group[1].ranking
        annotated.append(
            case.model_copy(
                update={
                    "invariants": case.invariants.model_copy(
                        update={"duplicate_idempotency": identical}
                    )
                }
            )
        )
    return tuple(annotated)
