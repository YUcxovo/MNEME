"""Tests for descriptive behavior summaries and paired comparisons."""

import statistics
from pathlib import Path

import pytest

from mneme.evaluation.behavior.analysis import build_summary
from mneme.evaluation.behavior.fixtures import load_behavior_fixtures
from mneme.evaluation.behavior.harness import run_behavior_evaluation

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs/evaluation/behavior/fixtures/behavior_controlled_v1.json"
)


@pytest.mark.base
def test_summary_is_deterministic_complete_and_explicitly_synthetic() -> None:
    fixture = load_behavior_fixtures(FIXTURE_PATH)
    cases = run_behavior_evaluation(fixture)

    first = build_summary(fixture, cases)
    second = build_summary(fixture, cases)

    assert first == second
    assert first.schema_version == "behavior-evaluation-summary-v1"
    assert first.controlled_synthetic is True
    assert first.fixture_version == "behavior-controlled-v1"
    assert len(first.model_configurations) == 9
    assert len(first.paired_comparisons) == 8 * 3
    assert len(first.mechanism_deltas) == 3 * 9
    assert first.invariant_failures == ()


@pytest.mark.base
def test_null_cold_start_metrics_are_excluded_from_aggregate_denominators() -> None:
    fixture = load_behavior_fixtures(FIXTURE_PATH)
    summary = build_summary(fixture, run_behavior_evaluation(fixture))
    overall = next(
        row
        for row in summary.aggregates
        if row.model_id == "behavior-v2"
        and row.metric == "ndcg_at_k"
        and row.scenario_family is None
    )

    assert overall.applicable_n == len(fixture.scenarios) - 1
    assert 0 <= overall.mean <= 1
    assert 0 <= overall.median <= 1


@pytest.mark.base
def test_paired_comparison_uses_same_scenarios_for_reference_and_baseline() -> None:
    fixture = load_behavior_fixtures(FIXTURE_PATH)
    cases = run_behavior_evaluation(fixture)
    summary = build_summary(fixture, cases)
    reported = next(
        row
        for row in summary.paired_comparisons
        if row.comparator_model == "behavior-v1" and row.metric == "ndcg_at_k"
    )
    by_key = {(case.scenario_id, case.model_id): case for case in cases}
    differences = []
    for scenario in fixture.scenarios:
        reference = by_key[(scenario.scenario_id, "behavior-v2")].metrics.ndcg_at_k
        baseline = by_key[(scenario.scenario_id, "behavior-v1")].metrics.ndcg_at_k
        if reference is not None and baseline is not None:
            differences.append(reference - baseline)

    assert reported.applicable_n == len(differences)
    assert reported.mean_delta == round(
        statistics.fmean(differences), fixture.evaluation.round_digits
    )
    assert reported.interval_lower <= reported.mean_delta <= reported.interval_upper


@pytest.mark.base
def test_mechanism_deltas_freeze_rank_direction_and_duplicate_zero() -> None:
    fixture = load_behavior_fixtures(FIXTURE_PATH)
    summary = build_summary(fixture, run_behavior_evaluation(fixture))
    duplicate = [row for row in summary.mechanism_deltas if row.pair_id == "duplicate-replay-01"]
    exposed = next(
        row
        for row in summary.mechanism_deltas
        if row.pair_id == "exposed-negative-01" and row.model_id == "behavior-v2"
    )

    assert len(duplicate) == 9
    assert all(row.duplicate_max_abs_score_delta == 0 for row in duplicate)
    assert exposed.target_rank_delta is not None
    assert exposed.target_rank_delta > 0
    assert exposed.target_score_delta is not None
    assert exposed.target_score_delta < 0


@pytest.mark.base
def test_summary_rejects_an_incomplete_case_matrix() -> None:
    fixture = load_behavior_fixtures(FIXTURE_PATH)
    cases = run_behavior_evaluation(fixture)

    with pytest.raises(ValueError, match="missing declared"):
        build_summary(fixture, cases[:-1])
