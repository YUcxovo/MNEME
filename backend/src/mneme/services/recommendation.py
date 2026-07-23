"""Assemble recommended digests from stored preferences and recent papers."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import structlog

from mneme.ai.recommendation import PaperCandidate, PreferenceView, rank_candidates
from mneme.models.base import utc_now
from mneme.models.digest import Digest, DigestEntry, DigestType
from mneme.models.paper import Paper
from mneme.repositories.digests import DigestRepository

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DigestBundle:
    """A digest, its ranked entries, and the resolved papers they point at.

    Entries are carried explicitly so callers never trigger lazy loads on a
    freshly created ORM digest.
    """

    digest: Digest
    entries: list[DigestEntry]
    papers_by_id: dict[UUID, Paper]


GENERATOR_VERSION = "recommender-v1"

# Bound the scoring pool: enough recent papers to rank meaningfully without
# unbounded scans at demo scale.
_CANDIDATE_POOL_LIMIT = 200
_FRESHNESS = timedelta(hours=24)


class RecommendedDigestService:
    """Serve a fresh manual digest or generate and persist a new one."""

    def __init__(
        self,
        repository: DigestRepository,
        *,
        candidate_days: int,
        max_entries: int,
    ) -> None:
        self._repository = repository
        self._candidate_days = candidate_days
        self._max_entries = max_entries

    async def get_or_generate(self, user_id: UUID) -> DigestBundle:
        """Return a digest for the user, reusing one generated recently.

        Generation is deterministic given stored preferences, candidates,
        and embeddings, so serving the fresh snapshot instead of rescoring
        keeps the endpoint cheap and reproducible.
        """
        fresh = await self._repository.get_fresh_recommended_digest(
            user_id=user_id, max_age=_FRESHNESS
        )
        if fresh is not None:
            fresh_entries = list(fresh.entries)
            return DigestBundle(
                digest=fresh,
                entries=fresh_entries,
                papers_by_id={entry.paper_id: entry.paper for entry in fresh_entries},
            )

        return await self.generate(
            user_id,
            digest_type=DigestType.MANUAL,
            as_of=utc_now(),
        )

    async def generate(
        self,
        user_id: UUID,
        *,
        digest_type: DigestType,
        as_of: datetime,
    ) -> DigestBundle:
        """Persist a deterministic digest snapshot for one cutoff instant."""
        if as_of.tzinfo is None:
            raise ValueError("Digest generation cutoff must be timezone-aware.")
        preference_row = await self._repository.get_preferences(user_id)
        preferences = PreferenceView(
            explicit_topics=tuple(preference_row.explicit_topics)
            if preference_row is not None
            else (),
            behavior_embedding=tuple(preference_row.behavior_embedding)
            if preference_row is not None and preference_row.behavior_embedding is not None
            else None,
            model_version=preference_row.model_version if preference_row is not None else 1,
        )

        papers = await self._repository.list_recent_candidates(
            since=as_of - timedelta(days=self._candidate_days),
            limit=_CANDIDATE_POOL_LIMIT,
            before=as_of,
        )
        embeddings = (
            await self._repository.mean_chunk_embeddings(
                [paper.id for paper in papers],
                embedding_model=preference_row.behavior_embedding_model,
            )
            if preference_row is not None
            and preference_row.behavior_embedding is not None
            and preference_row.behavior_embedding_model is not None
            else {}
        )
        candidates = [
            PaperCandidate(
                paper_id=paper.id,
                title=paper.title,
                categories=tuple(paper.categories),
                published_at=paper.published_at,
                embedding=embeddings.get(paper.id),
            )
            for paper in papers
        ]

        ranked = rank_candidates(candidates, preferences, now=as_of, limit=self._max_entries)
        entries = [
            DigestEntry(
                paper_id=scored.paper_id,
                rank=position + 1,
                relevance_score=scored.score,
                recommendation_reason="; ".join(scored.reasons),
            )
            for position, scored in enumerate(ranked)
        ]
        digest = await self._repository.create_digest(
            user_id=user_id,
            digest_type=digest_type,
            preference_model_version=preferences.model_version,
            generator_version=GENERATOR_VERSION,
            entries=entries,
        )
        logger.info(
            "recommended_digest_generated",
            user_id=str(user_id),
            digest_type=digest_type.value,
            entries=len(entries),
            candidates=len(candidates),
        )
        return DigestBundle(
            digest=digest,
            entries=entries,
            papers_by_id={paper.id: paper for paper in papers},
        )
