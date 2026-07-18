"""Frozen v0.1 Q&A request and response schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from mneme.ai.qa import GroundedAnswer
from mneme.models.qa import QaSourceMatchStatus


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
    """A grounded answer with verified citations."""

    answer: str
    citations: list[Citation]
    source_match_status: QaSourceMatchStatus
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
            conversation_id=conversation_id,
        )
