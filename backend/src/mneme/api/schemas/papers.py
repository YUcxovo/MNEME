"""Frozen v0.1 paper catalog response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel

from mneme.models.paper import Paper as PaperModel
from mneme.models.paper import ProcessingStatus


class Paper(BaseModel):
    """Public paper metadata with ordered display-name authors."""

    id: UUID
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    primary_category: str
    categories: list[str]
    pdf_url: AnyHttpUrl
    source_license: str | None = None
    processing_status: ProcessingStatus
    published_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, paper: PaperModel) -> Paper:
        """Map an eagerly loaded ORM paper to the public contract."""
        return cls(
            id=paper.id,
            arxiv_id=paper.arxiv_id,
            title=paper.title,
            authors=[link.author.display_name for link in paper.author_links],
            abstract=paper.abstract,
            primary_category=paper.primary_category,
            categories=list(paper.categories),
            pdf_url=paper.pdf_url,
            source_license=paper.source_license,
            processing_status=paper.processing_status,
            published_at=paper.published_at,
            updated_at=paper.source_updated_at,
        )


class PaperPage(BaseModel):
    """Cursor-paginated paper response."""

    items: list[Paper]
    next_cursor: str | None = None
