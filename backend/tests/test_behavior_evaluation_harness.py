"""Controlled replay tests for behavior baselines and mechanism ablations."""

from pathlib import Path

import pytest

from mneme.evaluation.behavior.fixtures import load_behavior_fixtures
from mneme.evaluation.behavior.harness import run_behavior_evaluation
from mneme.evaluation.behavior.models import BehaviorCaseResult, evaluation_models
from mneme.services.behavior_v2 import DEFAULT_BEHAVIOR_CONFIG

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs/evaluation/behavior/fixtures/behavior_controlled_v1.json"
)


def _results() -> tuple[BehaviorCaseResult, ...]:
    return run_behavior_evaluation(load_behavior_fixtures(FIXTURE_PATH))


def _case(
    results: tuple[BehaviorCaseResult, ...], scenario_id: str, model_id: str
) -> BehaviorCaseResult:
    return next(
        case for case in results if case.scenario_id == scenario_id and case.model_id == model_id
    )


@pytest.mark.base
def test_registry_contains_four_headline_models_and_five_ablation_models() -> None:
    models = evaluation_models()

    assert [model.model_id for model in models if model.headline] == [
        "recency-only",
        "explicit-recency",
        "behavior-v1",
        "behavior-v2",
    ]
    assert [model.model_id for model in models if not model.headline] == [
        "v2-single-timescale",
        "v2-no-saturation",
        "v2-no-exposure-gate",
        "v2-no-negative-channel",
        "v2-no-confidence-gate",
    ]
    assert len({model.model_id for model in models}) == 9
    assert all(model.configuration_payload()["model_id"] == model.model_id for model in models)


@pytest.mark.base
def test_complete_replay_is_byte_stable_and_uses_every_case_model_pair() -> None:
    fixture = load_behavior_fixtures(FIXTURE_PATH)
    first = run_behavior_evaluation(fixture)
    second = run_behavior_evaluation(fixture)

    assert first == second
    assert len(first) == len(fixture.scenarios) * len(evaluation_models()) == 108
    assert all(case.invariants.deterministic_replay for case in first)
    assert all(case.invariants.finite_scores for case in first)
    assert all(case.invariants.bounded_scores for case in first)
    assert all(case.invariants.stable_tie_break for case in first)


@pytest.mark.base
def test_model_identity_distinguishes_frozen_v1_and_configured_v2() -> None:
    results = _results()
    v1 = _case(results, "stable-positive-01", "behavior-v1")
    v2 = _case(results, "stable-positive-01", "behavior-v2")

    assert v1.model_version == 1
    assert v1.parameter_hash is None
    assert v1.profile_confidence is None
    assert v2.model_version == 2
    assert v2.parameter_hash == DEFAULT_BEHAVIOR_CONFIG.parameter_hash()
    assert v2.profile_confidence is not None and 0 < v2.profile_confidence < 1


@pytest.mark.base
def test_cold_start_retains_zero_confidence_and_null_relevance_metrics() -> None:
    case = _case(_results(), "cold-start-01", "behavior-v2")

    assert case.profile_confidence == 0
    assert case.metrics.ndcg_at_k is None
    assert case.metrics.recall_at_k is None
    assert case.metrics.reciprocal_rank is None
    assert case.metrics.target_rank is None


@pytest.mark.base
def test_exposure_gate_rejects_an_unobserved_skip() -> None:
    results = _results()
    complete = _case(results, "unexposed-skip-01", "behavior-v2")
    no_gate = _case(results, "unexposed-skip-01", "v2-no-exposure-gate")

    assert complete.invariants.exposure_gate is True
    assert no_gate.invariants.exposure_gate is False
    assert complete.metrics.target_score != no_gate.metrics.target_score
    assert complete.profile_confidence != no_gate.profile_confidence


@pytest.mark.base
def test_saturation_limits_repeated_same_paper_dominance() -> None:
    results = _results()
    complete = _case(results, "repeated-paper-01", "behavior-v2")
    no_saturation = _case(results, "repeated-paper-01", "v2-no-saturation")

    assert complete.profile_confidence is not None
    assert no_saturation.profile_confidence is not None
    assert complete.profile_confidence < no_saturation.profile_confidence
    assert complete.metrics.target_rank is not None
    assert no_saturation.metrics.target_rank is not None
    assert complete.metrics.target_rank < no_saturation.metrics.target_rank


@pytest.mark.base
def test_negative_channel_and_confidence_gate_change_only_declared_mechanisms() -> None:
    results = _results()
    contrastive = _case(results, "exposed-negative-01-after", "behavior-v2")
    no_negative = _case(results, "exposed-negative-01-after", "v2-no-negative-channel")
    confident = _case(results, "stable-positive-01", "v2-no-confidence-gate")
    calibrated = _case(results, "stable-positive-01", "behavior-v2")

    assert contrastive.metrics.target_rank is not None
    assert no_negative.metrics.target_rank is not None
    assert contrastive.metrics.target_rank > no_negative.metrics.target_rank
    assert contrastive.metrics.target_score is not None
    assert no_negative.metrics.target_score is not None
    assert contrastive.metrics.target_score < no_negative.metrics.target_score
    assert confident.profile_confidence == calibrated.profile_confidence
    assert confident.metrics.target_score != calibrated.metrics.target_score


@pytest.mark.base
def test_duplicate_replay_pairs_have_identical_rankings_for_every_model() -> None:
    duplicate_cases = [
        case for case in _results() if case.scenario_family.value == "duplicate_replay"
    ]

    assert len(duplicate_cases) == 18
    assert all(case.invariants.duplicate_idempotency is True for case in duplicate_cases)
    for model_id in {case.model_id for case in duplicate_cases}:
        pair = [case for case in duplicate_cases if case.model_id == model_id]
        assert pair[0].ranking == pair[1].ranking
