"""Immutable values returned by the arXiv metadata parser."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ArxivAuthorRecord:
    """An author as represented in an Atom entry."""

    name: str
    affiliation: str | None = None


@dataclass(frozen=True, slots=True)
class ArxivPaperRecord:
    """Normalized metadata for one observed arXiv revision."""

    arxiv_id: str
    version_number: int
    title: str
    abstract: str
    authors: tuple[ArxivAuthorRecord, ...]
    categories: tuple[str, ...]
    primary_category: str
    published_at: datetime
    updated_at: datetime
    abstract_url: str
    pdf_url: str
    source_license: str | None
    doi: str | None
    comment: str | None
    journal_reference: str | None


@dataclass(frozen=True, slots=True)
class ArxivFeed:
    """A parsed page of arXiv search results."""

    records: tuple[ArxivPaperRecord, ...]
    total_results: int
    start_index: int
    items_per_page: int
