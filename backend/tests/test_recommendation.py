"""Recommendation scoring: signals, blending, reasons, determinism."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from mneme.ai.recommendation import (
    BehaviorScoringConfig,
    PaperCandidate,
    PreferenceView,
    cosine_similarity,
    rank_candidates,
    recency_score,
    score_paper,
    topic_match,
)

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def _candidate(
    *,
    title: str = "Attention networks for retrieval",
    categories: tuple[str, ...] = ("cs.AI",),
    age_days: float = 1.0,
    embedding: tuple[float, ...] | None = None,
) -> PaperCandidate:
    return PaperCandidate(
        paper_id=uuid4(),
        title=title,
        categories=categories,
        published_at=NOW - timedelta(days=age_days),
        embedding=embedding,
    )


@pytest.mark.base
def test_cosine_similarity_bounds_and_degenerate_inputs() -> None:
    assert cosine_similarity((1.0, 0.0), (1.0, 0.0)) == 1.0
    assert cosine_similarity((1.0, 0.0), (-1.0, 0.0)) == 0.0
    assert cosine_similarity((0.0, 0.0), (1.0, 0.0)) == 0.0
    assert cosine_similarity((1.0,), (1.0, 0.0)) == 0.0


@pytest.mark.base
def test_topic_match_covers_title_and_categories() -> None:
    candidate = _candidate(title="Diffusion models for robotics", categories=("cs.RO",))

    strength, matched = topic_match(("diffusion", "cs.ro", "quantum"), candidate)

    assert strength == pytest.approx(2 / 3)
    assert matched == ("diffusion", "cs.ro")


@pytest.mark.base
def test_recency_decays_with_a_one_week_half_life() -> None:
    fresh = recency_score(NOW, now=NOW)
    week_old = recency_score(NOW - timedelta(days=7), now=NOW)

    assert fresh == pytest.approx(1.0)
    assert week_old == pytest.approx(0.5)


@pytest.mark.base
def test_matched_topics_appear_in_reasons() -> None:
    preferences = PreferenceView(explicit_topics=("attention", "quantization"))
    candidate = _candidate(title="Attention is all you need")

    scored = score_paper(candidate, preferences, now=NOW)

    assert any("attention" in reason for reason in scored.reasons)
    assert 0 <= scored.score <= 1


@pytest.mark.base
def test_behavior_similarity_lifts_the_score() -> None:
    embedding = (1.0, 0.0, 0.0)
    preferences_plain = PreferenceView(explicit_topics=("attention",))
    preferences_similar = PreferenceView(
        explicit_topics=("attention",), behavior_embedding=embedding
    )
    candidate = _candidate(title="Attention networks", embedding=embedding)

    without_behavior = score_paper(candidate, preferences_plain, now=NOW)
    with_behavior = score_paper(candidate, preferences_similar, now=NOW)

    assert with_behavior.score >= without_behavior.score
    assert any("engaged" in reason for reason in with_behavior.reasons)


@pytest.mark.base
def test_v1_scoring_ignores_v2_state_and_preserves_the_frozen_baseline() -> None:
    candidate = _candidate(embedding=(1.0, 0.0))
    baseline = PreferenceView(behavior_embedding=(1.0, 0.0), model_version=1)
    migrated = PreferenceView(
        behavior_embedding=(1.0, 0.0),
        negative_behavior_embedding=(1.0, 0.0),
        behavior_confidence=0.0,
        model_version=1,
    )

    assert score_paper(candidate, baseline, now=NOW) == score_paper(candidate, migrated, now=NOW)


@pytest.mark.base
def test_v2_zero_confidence_falls_back_to_cold_start_scoring() -> None:
    candidate = _candidate(embedding=(1.0, 0.0))
    cold_start = score_paper(candidate, PreferenceView(), now=NOW)
    uncertain = score_paper(
        candidate,
        PreferenceView(
            behavior_embedding=(1.0, 0.0),
            behavior_confidence=0.0,
            model_version=2,
        ),
        now=NOW,
    )

    assert uncertain == cold_start
    assert not any("reading pattern" in reason for reason in uncertain.reasons)


@pytest.mark.base
def test_v2_contrastive_channels_reward_positive_and_suppress_negative_matches() -> None:
    preferences = PreferenceView(
        behavior_embedding=(1.0, 0.0),
        negative_behavior_embedding=(0.0, 1.0),
        behavior_confidence=1.0,
        model_version=2,
    )
    positive = score_paper(_candidate(embedding=(1.0, 0.0)), preferences, now=NOW)
    negative = score_paper(_candidate(embedding=(0.0, 1.0)), preferences, now=NOW)

    assert positive.score > negative.score
    assert any("reading pattern" in reason for reason in positive.reasons)
    assert not any("reading pattern" in reason for reason in negative.reasons)


@pytest.mark.base
def test_v2_confidence_and_negative_channel_are_explicit_scoring_mechanisms() -> None:
    candidate = _candidate(age_days=7, embedding=(1.0, 0.0))
    low_confidence = PreferenceView(
        behavior_embedding=(1.0, 0.0), behavior_confidence=0.1, model_version=2
    )
    high_confidence = low_confidence.model_copy(update={"behavior_confidence": 1.0})
    negative_only = PreferenceView(
        negative_behavior_embedding=(1.0, 0.0),
        behavior_confidence=1.0,
        model_version=2,
    )

    assert (
        score_paper(candidate, high_confidence, now=NOW).score
        > score_paper(candidate, low_confidence, now=NOW).score
    )
    full = score_paper(candidate, negative_only, now=NOW)
    ablated = score_paper(
        candidate,
        negative_only,
        now=NOW,
        behavior_config=BehaviorScoringConfig(use_negative_channel=False),
    )
    assert full.score < ablated.score


@pytest.mark.base
def test_cold_start_user_still_gets_scores_and_reasons() -> None:
    scored = score_paper(_candidate(age_days=0.5), PreferenceView(), now=NOW)

    assert scored.score > 0
    assert scored.reasons


@pytest.mark.base
def test_ranking_is_deterministic_and_bounded() -> None:
    preferences = PreferenceView(explicit_topics=("attention",))
    candidates = [
        _candidate(title="Attention transformers", age_days=1),
        _candidate(title="Unrelated survey", age_days=1),
        _candidate(title="Attention distillation", age_days=10),
    ]

    first = rank_candidates(candidates, preferences, now=NOW, limit=2)
    second = rank_candidates(candidates, preferences, now=NOW, limit=2)

    assert first == second
    assert len(first) == 2
    assert first[0].score >= first[1].score
    assert first[0].paper_id in {candidates[0].paper_id, candidates[2].paper_id}
