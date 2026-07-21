"""Shared contracts for parsed paper documents."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mneme.models.paper import ParseQuality


class ParsedSection(BaseModel):
    """One logical section produced by parsing and consumed by AI services."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str | None = Field(default=None, max_length=300)
    text: str = Field(min_length=1)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_page_range(self) -> Self:
        """Reject a backwards page range while allowing unknown endpoints."""
        if (self.page_start is None) != (self.page_end is None):
            raise ValueError("page_start and page_end must both be set or both be absent")
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end must not be smaller than page_start")
        return self


class ParsedDocument(BaseModel):
    """Versioned parser output persisted between pipeline stages."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(default="1", min_length=1, max_length=32)
    parser_version: str = Field(min_length=1, max_length=64)
    paper_id: UUID
    paper_version_id: UUID
    source_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    parse_quality: ParseQuality
    page_count: int = Field(ge=0)
    sections: list[ParsedSection] = Field(min_length=1)
    fallback_reason: str | None = Field(default=None, max_length=128)
    parsed_at: datetime

    @model_validator(mode="after")
    def validate_document_metadata(self) -> Self:
        """Keep timestamps and page ranges internally consistent."""
        if self.parsed_at.tzinfo is None or self.parsed_at.utcoffset() is None:
            raise ValueError("parsed_at must include a timezone")
        if self.page_count == 0 and any(
            section.page_start is not None for section in self.sections
        ):
            raise ValueError("sections cannot reference pages when page_count is zero")
        if any(
            section.page_end is not None and section.page_end > self.page_count
            for section in self.sections
        ):
            raise ValueError("section page range exceeds page_count")
        return self
