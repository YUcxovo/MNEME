"""Validated values returned by the Semantic Scholar graph API."""

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

_ARXIV_VERSION = re.compile(r"v\d+$", re.IGNORECASE)


class CitationDirection(StrEnum):
    """Neighbor relationship requested from Semantic Scholar."""

    CITATIONS = "citations"
    REFERENCES = "references"

    @property
    def nested_paper_key(self) -> str:
        """Provider field containing the related paper."""
        if self is CitationDirection.CITATIONS:
            return "citingPaper"
        return "citedPaper"


class SemanticPaper(BaseModel):
    """The stable provider identity needed for citation persistence."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    paper_id: str = Field(alias="paperId", min_length=1, max_length=200)
    external_ids: dict[str, str] | None = Field(default=None, alias="externalIds")

    @property
    def arxiv_id(self) -> str | None:
        """Return a normalized unversioned arXiv work ID when supplied."""
        if self.external_ids is None:
            return None
        value = self.external_ids.get("ArXiv")
        if value is None:
            return None
        normalized = value.strip()
        if normalized.casefold().startswith("arxiv:"):
            normalized = normalized[6:]
        normalized = _ARXIV_VERSION.sub("", normalized)
        return normalized or None
