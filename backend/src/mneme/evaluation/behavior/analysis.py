"""Descriptive aggregation and paired comparisons for behavior replay."""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, ConfigDict

from mneme.evaluation.behavior.fixtures import BehaviorFixtureFile, ScenarioFamily, ScenarioPhase
from mneme.evaluation.behavior.metrics import percentile_bootstrap_interval
from mneme.evaluation.behavior.models import (
    BehaviorCaseResult,
    CaseMetrics,
    evaluation_models,
)

MetricName = Literal["ndcg_at_k", "recall_at_k", "reciprocal_rank"]
METRIC_NAMES: tuple[MetricName, ...] = ("ndcg_at_k", "recall_at_k", "reciprocal_rank")


class MetricAggregate(BaseModel):
    """Descriptive values for one model, metric, and optional family."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str
    metric: MetricName
    scenario_family: ScenarioFamily | None
    applicable_n: int
    mean: float
    median: float


class PairedModelComparison(BaseModel):
    """Paired behavior-v2 minus comparator differences."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference_model: Literal["behavior-v2"] = "behavior-v2"
    comparator_model: str
    metric: MetricName
    applicable_n: int
    mean_delta: float
    median_delta: float
    interval_lower: float
    interval_upper: float


class MechanismDelta(BaseModel):
    """Before-after or duplicate-replay change for one paired trace."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pair_id: str
    scenario_family: ScenarioFamily
    model_id: str
    target_rank_delta: int | None = None
    target_score_delta: float | None = None
    duplicate_max_abs_score_delta: float | None = None


class BehaviorEvaluationSummary(BaseModel):
    """Complete machine-readable summary without interpretive claims."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["behavior-evaluation-summary-v1"] = "behavior-evaluation-summary-v1"
    fixture_version: str
    controlled_synthetic: bool
    evaluation_settings: dict[str, int | float]
    model_configurations: tuple[dict[str, object], ...]
    aggregates: tuple[MetricAggregate, ...]
    paired_comparisons: tuple[PairedModelComparison, ...]
    mechanism_deltas: tuple[MechanismDelta, ...]
    invariant_failures: tuple[str, ...]


def build_summary(
    fixture: BehaviorFixtureFile,
    cases: tuple[BehaviorCaseResult, ...],
) -> BehaviorEvaluationSummary:
    """Aggregate cases according to the frozen analysis protocol."""
    expected = len(fixture.scenarios) * len(evaluation_models())
    if len(cases) != expected:
        raise ValueError("Behavior evaluation is missing declared scenario-model cases.")
    digits = fixture.evaluation.round_digits
    return BehaviorEvaluationSummary(
        fixture_version=fixture.fixture_version,
        controlled_synthetic=fixture.controlled_synthetic,
        evaluation_settings=fixture.evaluation.model_dump(),
        model_configurations=tuple(model.configuration_payload() for model in evaluation_models()),
        aggregates=_aggregate_metrics(cases, digits=digits),
        paired_comparisons=_paired_comparisons(fixture, cases, digits=digits),
        mechanism_deltas=_mechanism_deltas(cases, digits=digits),
        invariant_failures=_invariant_failures(cases),
    )


def _aggregate_metrics(
    cases: tuple[BehaviorCaseResult, ...], *, digits: int
) -> tuple[MetricAggregate, ...]:
    rows: list[MetricAggregate] = []
    model_ids = [model.model_id for model in evaluation_models()]
    for model_id in model_ids:
        model_cases = [case for case in cases if case.model_id == model_id]
        scopes: list[ScenarioFamily | None] = [None, *ScenarioFamily]
        for family in scopes:
            scoped = (
                model_cases
                if family is None
                else [case for case in model_cases if case.scenario_family is family]
            )
            for metric in METRIC_NAMES:
                values = [
                    value
                    for case in scoped
                    if (value := _metric_value(case.metrics, metric)) is not None
                ]
                if values:
                    rows.append(
                        MetricAggregate(
                            model_id=model_id,
                            metric=metric,
                            scenario_family=family,
                            applicable_n=len(values),
                            mean=round(statistics.fmean(values), digits),
                            median=round(statistics.median(values), digits),
                        )
                    )
    return tuple(rows)


def _paired_comparisons(
    fixture: BehaviorFixtureFile,
    cases: tuple[BehaviorCaseResult, ...],
    *,
    digits: int,
) -> tuple[PairedModelComparison, ...]:
    by_key = {(case.scenario_id, case.model_id): case for case in cases}
    comparisons: list[PairedModelComparison] = []
    for comparator in evaluation_models():
        if comparator.model_id == "behavior-v2":
            continue
        for metric in METRIC_NAMES:
            differences: list[float] = []
            for scenario in fixture.scenarios:
                reference = _metric_value(
                    by_key[(scenario.scenario_id, "behavior-v2")].metrics, metric
                )
                compared = _metric_value(
                    by_key[(scenario.scenario_id, comparator.model_id)].metrics, metric
                )
                if reference is not None and compared is not None:
                    differences.append(reference - compared)
            interval = percentile_bootstrap_interval(
                differences,
                seed=fixture.evaluation.bootstrap_seed,
                replicates=fixture.evaluation.bootstrap_replicates,
                confidence=fixture.evaluation.confidence_interval,
            )
            if interval is not None:
                comparisons.append(
                    PairedModelComparison(
                        comparator_model=comparator.model_id,
                        metric=metric,
                        applicable_n=interval.applicable_n,
                        mean_delta=round(interval.mean, digits),
                        median_delta=round(interval.median, digits),
                        interval_lower=round(interval.lower, digits),
                        interval_upper=round(interval.upper, digits),
                    )
                )
    return tuple(comparisons)


def _mechanism_deltas(
    cases: tuple[BehaviorCaseResult, ...], *, digits: int
) -> tuple[MechanismDelta, ...]:
    groups: dict[tuple[str, str], list[BehaviorCaseResult]] = defaultdict(list)
    for case in cases:
        if case.pair_id is not None:
            groups[(case.pair_id, case.model_id)].append(case)

    deltas: list[MechanismDelta] = []
    for (pair_id, model_id), pair in sorted(groups.items()):
        before = next((case for case in pair if case.phase is ScenarioPhase.BEFORE), None)
        after = next((case for case in pair if case.phase is ScenarioPhase.AFTER), None)
        replay = next((case for case in pair if case.phase is ScenarioPhase.REPLAY), None)
        rank_delta = None
        score_delta = None
        duplicate_delta = None
        if before is not None and after is not None:
            if before.metrics.target_rank is not None and after.metrics.target_rank is not None:
                rank_delta = after.metrics.target_rank - before.metrics.target_rank
            if before.metrics.target_score is not None and after.metrics.target_score is not None:
                score_delta = round(
                    after.metrics.target_score - before.metrics.target_score, digits
                )
        if before is not None and replay is not None:
            before_scores = {item.paper_id: item.score for item in before.ranking}
            duplicate_delta = round(
                max(abs(item.score - before_scores[item.paper_id]) for item in replay.ranking),
                digits,
            )
        deltas.append(
            MechanismDelta(
                pair_id=pair_id,
                scenario_family=pair[0].scenario_family,
                model_id=model_id,
                target_rank_delta=rank_delta,
                target_score_delta=score_delta,
                duplicate_max_abs_score_delta=duplicate_delta,
            )
        )
    return tuple(deltas)


def _invariant_failures(cases: tuple[BehaviorCaseResult, ...]) -> tuple[str, ...]:
    failures: list[str] = []
    for case in cases:
        exact = {
            "bounded_scores": case.invariants.bounded_scores,
            "deterministic_replay": case.invariants.deterministic_replay,
            "finite_scores": case.invariants.finite_scores,
            "stable_tie_break": case.invariants.stable_tie_break,
        }
        if case.invariants.duplicate_idempotency is not None:
            exact["duplicate_idempotency"] = case.invariants.duplicate_idempotency
        failures.extend(
            f"{case.scenario_id}:{case.model_id}:{name}"
            for name, passed in exact.items()
            if not passed
        )
    return tuple(sorted(failures))


def _metric_value(metrics: CaseMetrics, metric: MetricName) -> float | None:
    return getattr(metrics, metric)
