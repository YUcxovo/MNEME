"""Recommendation scoring against the frozen user-preference interface.

Scores blend three signals: explicit topic match, similarity between the
user's learned behavior embedding (owned by Ruiyu's behavioral model) and
the paper's mean chunk embedding, and publication recency. Every entry
carries human-readable reasons derived from its dominant signals.
"""

import math
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_TOPIC_WEIGHT = 0.45
_BEHAVIOR_WEIGHT = 0.35
_RECENCY_WEIGHT = 0.2
_RECENCY_HALF_LIFE_DAYS = 7.0
_MIN_REASON_COMPONENT = 0.15


class PaperCandidate(BaseModel):
    """The scoring view of one recent paper."""

    model_config = ConfigDict(frozen=True)

    paper_id: UUID
    title: str
    categories: tuple[str, ...]
    published_at: datetime
    embedding: tuple[float, ...] | None = None


class PreferenceView(BaseModel):
    """The scoring view of one user's stored preferences."""

    model_config = ConfigDict(frozen=True)

    explicit_topics: tuple[str, ...] = ()
    behavior_embedding: tuple[float, ...] | None = None
    model_version: int = Field(default=1, ge=1)


class ScoredPaper(BaseModel):
    """One ranked recommendation with its explanation."""

    model_config = ConfigDict(frozen=True)

    paper_id: UUID
    score: float = Field(ge=0, le=1)
    reasons: tuple[str, ...] = Field(min_length=1)


def cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Cosine similarity clamped to [0, 1]; 0 for degenerate vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def topic_match(
    topics: tuple[str, ...], candidate: PaperCandidate
) -> tuple[float, tuple[str, ...]]:
    """Fraction of explicit topics matching the paper, with the matches."""
    if not topics:
        return 0.0, ()
    title = candidate.title.casefold()
    categories = {category.casefold() for category in candidate.categories}
    matched = tuple(
        topic for topic in topics if topic.casefold() in title or topic.casefold() in categories
    )
    return len(matched) / len(topics), matched


def recency_score(published_at: datetime, *, now: datetime) -> float:
    """Exponential decay with a one-week half-life, clamped to [0, 1]."""
    age_days = max(0.0, (now - published_at).total_seconds() / 86_400)
    return 0.5 ** (age_days / _RECENCY_HALF_LIFE_DAYS)


def score_paper(
    candidate: PaperCandidate, preferences: PreferenceView, *, now: datetime
) -> ScoredPaper:
    """Blend topic, behavior, and recency signals into one scored entry.

    Missing signals (no explicit topics, no behavior embedding, no paper
    embedding) redistribute their weight over the available ones so a
    cold-start user still gets a meaningful [0, 1] score.
    """
    components: list[tuple[str, float, float]] = []

    if preferences.explicit_topics:
        strength, matched = topic_match(preferences.explicit_topics, candidate)
        label = (
            "Matches your topics: " + ", ".join(matched[:3])
            if matched
            else "Related to your chosen topics"
        )
        components.append((label, _TOPIC_WEIGHT, strength))

    if preferences.behavior_embedding is not None and candidate.embedding is not None:
        similarity = cosine_similarity(preferences.behavior_embedding, candidate.embedding)
        components.append(
            ("Similar to papers you recently engaged with", _BEHAVIOR_WEIGHT, similarity)
        )

    components.append(
        ("Recently published", _RECENCY_WEIGHT, recency_score(candidate.published_at, now=now))
    )

    total_weight = sum(weight for _, weight, _ in components)
    score = sum(weight * strength for _, weight, strength in components) / total_weight

    reasons = tuple(
        label
        for label, _, strength in sorted(components, key=lambda item: -item[2])
        if strength >= _MIN_REASON_COMPONENT
    ) or ("Recently published in your feed",)
    return ScoredPaper(paper_id=candidate.paper_id, score=round(score, 6), reasons=reasons)


def rank_candidates(
    candidates: list[PaperCandidate],
    preferences: PreferenceView,
    *,
    now: datetime,
    limit: int,
) -> list[ScoredPaper]:
    """Score all candidates and return the deterministic top-N."""
    scored = [score_paper(candidate, preferences, now=now) for candidate in candidates]
    scored.sort(key=lambda item: (-item.score, str(item.paper_id)))
    return scored[:limit]
