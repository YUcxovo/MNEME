"""Frozen v0.1 digest response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from mneme.api.schemas.papers import Paper
from mneme.models.digest import DigestType
from mneme.services.recommendation import DigestBundle


class DigestEntry(BaseModel):
    """One ranked paper with its recommendation explanation."""

    paper: Paper
    rank: int = Field(ge=1)
    relevance_score: float = Field(ge=0, le=1)
    recommendation_reason: str


class Digest(BaseModel):
    """An immutable research briefing."""

    id: UUID
    digest_type: DigestType
    generated_at: datetime
    entries: list[DigestEntry]

    @classmethod
    def from_bundle(cls, bundle: DigestBundle) -> Digest:
        """Map a generated or reloaded digest bundle to the public contract."""
        return cls(
            id=bundle.digest.id,
            digest_type=bundle.digest.digest_type,
            generated_at=bundle.digest.generated_at,
            entries=[
                DigestEntry(
                    paper=Paper.from_model(bundle.papers_by_id[entry.paper_id]),
                    rank=entry.rank,
                    relevance_score=entry.relevance_score,
                    recommendation_reason=entry.recommendation_reason,
                )
                for entry in sorted(bundle.entries, key=lambda item: item.rank)
            ],
        )
