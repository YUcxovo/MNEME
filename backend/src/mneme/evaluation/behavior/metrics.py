"""Pure ranking, diversity, and paired-bootstrap metrics."""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from mneme.ai.recommendation import cosine_similarity
from mneme.evaluation.behavior.fixtures import RelevanceJudgment


@dataclass(frozen=True, slots=True)
class BootstrapInterval:
    """Descriptive aggregate with a fixed-seed percentile interval."""

    applicable_n: int
    mean: float
    median: float
    lower: float
    upper: float


def ndcg_at_k(
    ranked_ids: Sequence[UUID],
    judgments: Mapping[UUID, RelevanceJudgment],
    *,
    k: int,
) -> float | None:
    """Return graded nDCG, or null when no eligible relevant item exists."""
    grades = _eligible_grades(judgments)
    if not grades:
        return None
    observed = [
        _gain(grades.get(paper_id, 0), rank) for rank, paper_id in enumerate(ranked_ids[:k], 1)
    ]
    ideal = [
        _gain(grade, rank)
        for rank, grade in enumerate(sorted(grades.values(), reverse=True)[:k], 1)
    ]
    ideal_dcg = math.fsum(ideal)
    return math.fsum(observed) / ideal_dcg if ideal_dcg > 0 else None


def recall_at_k(
    ranked_ids: Sequence[UUID],
    judgments: Mapping[UUID, RelevanceJudgment],
    *,
    k: int,
) -> float | None:
    """Return binary relevant-item recall at k."""
    relevant = set(_eligible_grades(judgments))
    if not relevant:
        return None
    return len(relevant.intersection(ranked_ids[:k])) / len(relevant)


def reciprocal_rank(
    ranked_ids: Sequence[UUID],
    judgments: Mapping[UUID, RelevanceJudgment],
) -> float | None:
    """Return reciprocal rank over the complete candidate ordering."""
    relevant = set(_eligible_grades(judgments))
    if not relevant:
        return None
    for rank, paper_id in enumerate(ranked_ids, 1):
        if paper_id in relevant:
            return 1 / rank
    return 0.0


def intra_list_diversity(
    ranked_ids: Sequence[UUID],
    embeddings: Mapping[UUID, Sequence[float]],
    *,
    k: int,
) -> float | None:
    """Return mean pairwise cosine distance for represented top-k items."""
    vectors = [tuple(embeddings[item]) for item in ranked_ids[:k] if item in embeddings]
    if len(vectors) < 2:
        return None
    distances = [
        1 - cosine_similarity(vectors[left], vectors[right])
        for left in range(len(vectors))
        for right in range(left + 1, len(vectors))
    ]
    return math.fsum(distances) / len(distances)


def percentile_bootstrap_interval(
    values: Sequence[float],
    *,
    seed: int,
    replicates: int,
    confidence: float,
) -> BootstrapInterval | None:
    """Summarize paired values with a deterministic percentile interval."""
    if not values:
        return None
    if replicates < 1:
        raise ValueError("Bootstrap replicates must be positive.")
    if not 0 < confidence < 1:
        raise ValueError("Bootstrap confidence must be between zero and one.")
    if any(not math.isfinite(value) for value in values):
        raise ValueError("Bootstrap values must be finite.")

    generator = random.Random(seed)
    sample_size = len(values)
    means = sorted(
        math.fsum(values[generator.randrange(sample_size)] for _ in range(sample_size))
        / sample_size
        for _ in range(replicates)
    )
    tail = (1 - confidence) / 2
    return BootstrapInterval(
        applicable_n=sample_size,
        mean=statistics.fmean(values),
        median=statistics.median(values),
        lower=_percentile(means, tail),
        upper=_percentile(means, 1 - tail),
    )


def _eligible_grades(
    judgments: Mapping[UUID, RelevanceJudgment],
) -> dict[UUID, int]:
    return {
        paper_id: judgment.grade
        for paper_id, judgment in judgments.items()
        if judgment.eligible and judgment.grade > 0
    }


def _gain(grade: int, rank: int) -> float:
    return (2**grade - 1) / math.log2(rank + 1)


def _percentile(sorted_values: Sequence[float], quantile: float) -> float:
    position = quantile * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction
