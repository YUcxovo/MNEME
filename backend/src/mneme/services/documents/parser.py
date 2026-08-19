"""Synchronous PDF parsing with an abstract-only safety net."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from mneme.models.paper import ParseQuality
from mneme.services.documents.parser_layout import (
    extract_headings,
    extract_text,
    normalize_line,
    split_at_headings,
    text_size,
)
from mneme.services.documents.types import ParsedDocument, ParsedSection

PARSER_VERSION = "pymupdf-pdfplumber-v3"


class PdfParseError(RuntimeError):
    """Safe parser failure raised only when no abstract fallback is available."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class PdfParser:
    """Parse one local PDF without database, queue, or event-loop side effects."""

    min_text_chars: int = 500
    parser_version: str = PARSER_VERSION

    def __post_init__(self) -> None:
        if self.min_text_chars < 1:
            raise ValueError("min_text_chars must be positive")
        if not self.parser_version:
            raise ValueError("parser_version must not be empty")

    def parse(
        self,
        source_path: Path,
        *,
        paper_id: UUID,
        paper_version_id: UUID,
        source_checksum: str,
        abstract: str,
        parsed_at: datetime,
    ) -> ParsedDocument:
        """Return validated parser output for one exact paper revision."""
        extraction = extract_text(source_path)
        extracted_text = "\n\n".join(page for page in extraction.pages if page)

        if extraction.failure_reason is not None:
            return self._abstract_fallback(
                paper_id=paper_id,
                paper_version_id=paper_version_id,
                source_checksum=source_checksum,
                abstract=abstract,
                parsed_at=parsed_at,
                page_count=extraction.page_count,
                reason=extraction.failure_reason,
            )
        if text_size(extracted_text) < self.min_text_chars:
            return self._abstract_fallback(
                paper_id=paper_id,
                paper_version_id=paper_version_id,
                source_checksum=source_checksum,
                abstract=abstract,
                parsed_at=parsed_at,
                page_count=extraction.page_count,
                reason="insufficient_text",
            )

        try:
            headings = extract_headings(source_path)
        except Exception:
            headings = {}
            text_only_reason = "structure_extraction_failed"
        else:
            text_only_reason = "section_headings_not_detected"

        sections = split_at_headings(extraction.pages, headings)
        if sections:
            quality = ParseQuality.STRUCTURED
            fallback_reason = None
        else:
            quality = ParseQuality.TEXT_ONLY
            fallback_reason = text_only_reason
            populated_pages = [
                number for number, text in enumerate(extraction.pages, start=1) if text
            ]
            sections = [
                ParsedSection(
                    text=extracted_text,
                    page_start=populated_pages[0],
                    page_end=populated_pages[-1],
                )
            ]

        return ParsedDocument(
            parser_version=self.parser_version,
            paper_id=paper_id,
            paper_version_id=paper_version_id,
            source_checksum=source_checksum,
            parse_quality=quality,
            page_count=extraction.page_count,
            sections=sections,
            fallback_reason=fallback_reason,
            parsed_at=parsed_at,
        )

    def _abstract_fallback(
        self,
        *,
        paper_id: UUID,
        paper_version_id: UUID,
        source_checksum: str,
        abstract: str,
        parsed_at: datetime,
        page_count: int,
        reason: str,
    ) -> ParsedDocument:
        normalized_abstract = normalize_line(abstract)
        if not normalized_abstract:
            raise PdfParseError(
                "abstract_unavailable",
                "The PDF was unusable and no abstract fallback was available.",
            )
        return ParsedDocument(
            parser_version=self.parser_version,
            paper_id=paper_id,
            paper_version_id=paper_version_id,
            source_checksum=source_checksum,
            parse_quality=ParseQuality.ABSTRACT_ONLY,
            page_count=page_count,
            sections=[ParsedSection(title="Abstract", text=normalized_abstract)],
            fallback_reason=reason,
            parsed_at=parsed_at,
        )
