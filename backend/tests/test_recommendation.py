"""Recommendation scoring: signals, blending, reasons, determinism."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from mneme.ai.recommendation import (
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
