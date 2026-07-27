"""Contract tests for controlled behavior-evaluation inputs."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from mneme.evaluation.behavior.fixtures import (
    BehaviorFixtureFile,
    BehaviorScenario,
    ScenarioFamily,
    load_behavior_fixtures,
    scenario_candidates,
    scenario_embeddings,
    scenario_signals,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs/evaluation/behavior/fixtures/behavior_controlled_v1.json"
)


def _fixture() -> BehaviorFixtureFile:
    return load_behavior_fixtures(FIXTURE_PATH)


@pytest.mark.base
def test_controlled_fixture_freezes_identity_settings_and_all_families() -> None:
    fixture = _fixture()

    assert fixture.schema_version == "behavior-controlled-fixture-v1"
    assert fixture.fixture_version == "behavior-controlled-v1"
    assert fixture.controlled_synthetic is True
    assert fixture.embedding_dimensions == 4
    assert fixture.evaluation.metric_k == 5
    assert fixture.evaluation.bootstrap_seed == 20260727
    assert fixture.evaluation.bootstrap_replicates == 10_000
    assert {scenario.family for scenario in fixture.scenarios} == set(ScenarioFamily)


@pytest.mark.base
def test_fixture_references_and_embeddings_are_fully_resolved() -> None:
    fixture = _fixture()
    paper_ids = {paper.paper_id for paper in fixture.papers}
    candidate_ids = {paper.paper_id for paper in fixture.papers if paper.candidate}

    assert len(paper_ids) == len(fixture.papers)
    assert all(
        paper.embedding is None or len(paper.embedding) == fixture.embedding_dimensions
        for paper in fixture.papers
    )
    for scenario in fixture.scenarios:
        assert set(scenario.candidate_ids) <= candidate_ids
        assert all(
            event.paper_id is None or event.paper_id in paper_ids for event in scenario.events
        )
        assert all(item.paper_id in scenario.candidate_ids for item in scenario.judgments)
        assert all(event.occurred_at <= fixture.reference_time_utc for event in scenario.events)


@pytest.mark.base
def test_fixture_adapters_use_production_input_types() -> None:
    fixture = _fixture()
    scenario = next(item for item in fixture.scenarios if item.scenario_id == "stable-positive-01")

    signals = scenario_signals(scenario)
    candidates = scenario_candidates(fixture, scenario)
    embeddings = scenario_embeddings(fixture)

    assert len(signals) == 2
    assert signals[1].duration_ms == 180_000
    assert [candidate.paper_id for candidate in candidates] == list(scenario.candidate_ids)
    assert all(candidate.embedding is not None for candidate in candidates)
    assert len(embeddings) == len(fixture.papers) - 1


@pytest.mark.base
def test_paired_cases_share_candidate_and_target_contracts() -> None:
    fixture = _fixture()
    pairs: dict[str, list[BehaviorScenario]] = {}
    for scenario in fixture.scenarios:
        if scenario.pair_id is not None:
            pairs.setdefault(scenario.pair_id, []).append(scenario)

    assert set(pairs) == {"interest-shift-01", "exposed-negative-01", "duplicate-replay-01"}
    for cases in pairs.values():
        assert len({case.candidate_ids for case in cases}) == 1
        assert len({case.target_paper_id for case in cases}) == 1

    replay = pairs["duplicate-replay-01"]
    assert replay[0].events == replay[1].events


@pytest.mark.base
@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update({"unexpected": True}),
        lambda payload: payload["papers"][0].update({"embedding": [1.0, 0.0]}),
        lambda payload: payload["scenarios"][0]["candidate_ids"].append(
            "00000000-0000-0000-0000-000000000999"
        ),
        lambda payload: payload["scenarios"][1]["events"][0].update(
            {"occurred_at": "2026-07-28T12:00:00Z"}
        ),
    ],
)
def test_invalid_fixture_mutations_fail_closed(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    payload = _fixture().model_dump(mode="json")
    mutation(payload)

    with pytest.raises(ValidationError):
        BehaviorFixtureFile.model_validate(payload)


@pytest.mark.base
def test_duplicate_event_identity_is_rejected_within_one_case() -> None:
    payload = _fixture().model_dump(mode="json")
    stable = payload["scenarios"][1]
    stable["events"].append(dict(stable["events"][0]))

    with pytest.raises(ValidationError, match="Duplicate event identity"):
        BehaviorFixtureFile.model_validate(payload)


@pytest.mark.base
def test_cold_start_deliberately_leaves_ranking_metrics_undefined() -> None:
    fixture = _fixture()
    cold_start = next(
        scenario for scenario in fixture.scenarios if scenario.family is ScenarioFamily.COLD_START
    )

    assert cold_start.events == ()
    assert cold_start.judgments == ()
    assert cold_start.target_paper_id is None
