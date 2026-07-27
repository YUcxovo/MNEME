"""Hand-calculated tests for controlled behavior-evaluation metrics."""

import math
from uuid import UUID

import pytest

from mneme.evaluation.behavior.fixtures import RelevanceJudgment
from mneme.evaluation.behavior.metrics import (
    intra_list_diversity,
    ndcg_at_k,
    percentile_bootstrap_interval,
    recall_at_k,
    reciprocal_rank,
)

PAPER_A = UUID("00000000-0000-0000-0000-000000000001")
PAPER_B = UUID("00000000-0000-0000-0000-000000000002")
PAPER_C = UUID("00000000-0000-0000-0000-000000000003")


def _judgments() -> dict[UUID, RelevanceJudgment]:
    return {
        PAPER_A: RelevanceJudgment(paper_id=PAPER_A, grade=3),
        PAPER_C: RelevanceJudgment(paper_id=PAPER_C, grade=1),
    }


@pytest.mark.base
def test_graded_ndcg_matches_a_hand_calculation() -> None:
    observed = 7 / math.log2(2) + 1 / math.log2(4)
    ideal = 7 / math.log2(2) + 1 / math.log2(3)

    assert ndcg_at_k([PAPER_A, PAPER_B, PAPER_C], _judgments(), k=3) == pytest.approx(
        observed / ideal
    )


@pytest.mark.base
def test_recall_and_reciprocal_rank_cover_hits_and_misses() -> None:
    ranking = [PAPER_B, PAPER_C, PAPER_A]

    assert recall_at_k(ranking, _judgments(), k=2) == 0.5
    assert recall_at_k(ranking, _judgments(), k=3) == 1.0
    assert reciprocal_rank(ranking, _judgments()) == 0.5
    assert reciprocal_rank([PAPER_B], _judgments()) == 0.0


@pytest.mark.base
def test_ranking_metrics_remain_null_without_eligible_relevance() -> None:
    ineligible = {
        PAPER_A: RelevanceJudgment(paper_id=PAPER_A, grade=3, eligible=False),
        PAPER_B: RelevanceJudgment(paper_id=PAPER_B, grade=0),
    }

    assert ndcg_at_k([PAPER_A, PAPER_B], ineligible, k=2) is None
    assert recall_at_k([PAPER_A, PAPER_B], ineligible, k=2) is None
    assert reciprocal_rank([PAPER_A, PAPER_B], ineligible) is None


@pytest.mark.base
def test_intra_list_diversity_uses_pairwise_cosine_distance() -> None:
    embeddings = {PAPER_A: (1.0, 0.0), PAPER_B: (0.0, 1.0), PAPER_C: (1.0, 0.0)}

    assert intra_list_diversity([PAPER_A, PAPER_B], embeddings, k=2) == pytest.approx(1.0)
    assert intra_list_diversity([PAPER_A], embeddings, k=1) is None
    assert intra_list_diversity([PAPER_C, PAPER_A], embeddings, k=2) == pytest.approx(0.0)


@pytest.mark.base
def test_fixed_seed_bootstrap_is_deterministic_and_descriptive() -> None:
    values = [0.1, 0.2, 0.3, 0.4]
    first = percentile_bootstrap_interval(values, seed=7, replicates=500, confidence=0.95)
    second = percentile_bootstrap_interval(values, seed=7, replicates=500, confidence=0.95)

    assert first == second
    assert first is not None
    assert first.applicable_n == 4
    assert first.mean == pytest.approx(0.25)
    assert first.median == pytest.approx(0.25)
    assert first.lower <= first.mean <= first.upper


@pytest.mark.base
def test_empty_or_invalid_bootstrap_inputs_fail_explicitly() -> None:
    assert percentile_bootstrap_interval([], seed=1, replicates=10, confidence=0.95) is None
    with pytest.raises(ValueError, match="positive"):
        percentile_bootstrap_interval([1.0], seed=1, replicates=0, confidence=0.95)
    with pytest.raises(ValueError, match="finite"):
        percentile_bootstrap_interval([float("nan")], seed=1, replicates=10, confidence=0.95)
