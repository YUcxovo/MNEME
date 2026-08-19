"""Frozen v0.1 summary response schema."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from mneme.ai.claim_provenance import SummaryClaim
from mneme.ai.summaries import mock_tldr
from mneme.ai.summarization import StructuredSummary
from mneme.models.artifact import PaperSummary, SourceMatchStatus, SummaryStatus
from mneme.models.paper import Paper as PaperModel


class ClaimProvenance(BaseModel):
    """One claim's validated source in the exact summarized revision."""

    chunk_id: UUID
    chunk_index: int
    section_title: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    excerpt: str


class SourcedClaim(BaseModel):
    """A key claim with its matched source or an explicit unmatched state."""

    text: str
    matched: bool
    source: ClaimProvenance | None = None

    @classmethod
    def from_claim(cls, claim: SummaryClaim) -> SourcedClaim:
        """Map internal provenance to the public contract."""
        source = (
            ClaimProvenance(
                chunk_id=claim.source.chunk_id,
                chunk_index=claim.source.chunk_index,
                section_title=claim.source.section_title,
                page_start=claim.source.page_start,
                page_end=claim.source.page_end,
                excerpt=claim.source.excerpt,
            )
            if claim.source is not None
            else None
        )
        return cls(text=claim.text, matched=claim.matched, source=source)


class Summary(BaseModel):
    """Structured paper summary as frozen in the v0.1 contract.

    ``claims`` extends the contract additively: ``key_claims`` keeps its
    plain-string shape for existing consumers, and each entry of ``claims``
    carries the same text plus revision-validated provenance (or an explicit
    unmatched marker). Summaries stored before provenance existed serialize
    with an empty ``claims`` list and ``source_match_status=not_checked``.
    """

    paper_id: UUID
    status: SummaryStatus
    tldr: str
    key_claims: list[str] = []
    methodology: str | None = None
    limitations: str | None = None
    source_match_status: SourceMatchStatus
    claims: list[SourcedClaim] = []

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

    @classmethod
    def from_stored(cls, stored: PaperSummary) -> Summary:
        """Map a persisted generated summary to the public contract."""
        content = StructuredSummary.model_validate(stored.content)
        return cls(
            paper_id=stored.paper_id,
            status=stored.status,
            tldr=content.tldr,
            key_claims=list(content.key_claims),
            methodology=content.methodology,
            limitations=content.limitations,
            source_match_status=stored.source_match_status,
            claims=[SourcedClaim.from_claim(claim) for claim in content.claims],
        )
