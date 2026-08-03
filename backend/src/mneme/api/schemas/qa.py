"""Frozen v0.1 Q&A request and response schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from mneme.ai.qa import GroundedAnswer
from mneme.models.qa import QaCitationResolution, QaSourceMatchStatus


class Question(BaseModel):
    """One user question scoped to a single paper."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=500)
    paper_id: UUID
    conversation_id: UUID | None = None


class Citation(BaseModel):
    """One citation pointing at a stored source chunk."""

    paper_id: UUID
    arxiv_id: str | None = None
    section_title: str
    chunk_id: UUID | None = None
    source_match: bool


class Answer(BaseModel):
    """A grounded answer with verified citations.

    ``citation_resolution`` and ``model_calls`` extend the contract
    additively: existing fields keep their frozen shapes, and the new fields
    state how the citation contract was resolved (first pass, one bounded
    correction, or an explicit unresolved state) and how many model calls
    the answer consumed.
    """

    answer: str
    citations: list[Citation]
    source_match_status: QaSourceMatchStatus
    citation_resolution: QaCitationResolution = QaCitationResolution.NOT_APPLICABLE
    model_calls: int = 0
    conversation_id: UUID

    @classmethod
    def from_grounded(
        cls, grounded: GroundedAnswer, *, arxiv_id: str, conversation_id: UUID
    ) -> Answer:
        """Map a verified generation result to the public contract."""
        return cls(
            answer=grounded.answer,
            citations=[
                Citation(
                    paper_id=citation.chunk.paper_id,
                    arxiv_id=arxiv_id,
                    section_title=citation.chunk.section_title or "",
                    chunk_id=citation.chunk.chunk_id,
                    source_match=citation.source_match,
                )
                for citation in grounded.citations
            ],
            source_match_status=grounded.source_match_status,
            citation_resolution=grounded.citation_resolution,
            model_calls=grounded.model_calls,
            conversation_id=conversation_id,
        )
