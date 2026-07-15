"""Frozen v0.1 summary response schema."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from mneme.ai.summaries import mock_tldr
from mneme.models.artifact import SourceMatchStatus, SummaryStatus
from mneme.models.paper import Paper as PaperModel


class Summary(BaseModel):
    """Structured paper summary as frozen in the v0.1 contract."""

    paper_id: UUID
    status: SummaryStatus
    tldr: str
    key_claims: list[str] = []
    methodology: str | None = None
    limitations: str | None = None
    source_match_status: SourceMatchStatus

    @classmethod
    def mock_from_paper(cls, paper: PaperModel) -> Summary:
        """Derive the Milestone 1 abstract-based placeholder summary."""
        return cls(
            paper_id=paper.id,
            status=SummaryStatus.PARTIAL,
            tldr=mock_tldr(paper.abstract),
            key_claims=[],
            source_match_status=SourceMatchStatus.NOT_CHECKED,
        )
