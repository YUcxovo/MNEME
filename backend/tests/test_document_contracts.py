"""Shared contracts between document parsing and AI chunking."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from mneme.ai.chunking import ParsedSection as ChunkingParsedSection
from mneme.models.paper import ParseQuality
from mneme.services.documents import ParsedDocument, ParsedSection

PAPER_ID = UUID("11111111-1111-4111-8111-111111111111")
VERSION_ID = UUID("22222222-2222-4222-8222-222222222222")


def _document() -> ParsedDocument:
    return ParsedDocument(
        parser_version="parser-v1",
        paper_id=PAPER_ID,
        paper_version_id=VERSION_ID,
        source_checksum="a" * 64,
        parse_quality=ParseQuality.STRUCTURED,
        page_count=2,
        sections=[
            ParsedSection(
                title="Introduction",
                text="A compact parsed section.",
                page_start=1,
                page_end=2,
            )
        ],
        parsed_at=datetime(2026, 7, 21, tzinfo=UTC),
    )


@pytest.mark.base
@pytest.mark.pipeline
def test_chunking_reexports_the_shared_section_contract() -> None:
    assert ChunkingParsedSection is ParsedSection


@pytest.mark.base
@pytest.mark.pipeline
def test_parsed_section_rejects_backwards_page_range() -> None:
    with pytest.raises(ValueError, match="page_end must not be smaller"):
        ParsedSection(text="Invalid pages", page_start=3, page_end=2)


@pytest.mark.base
@pytest.mark.pipeline
def test_parsed_section_requires_complete_page_range() -> None:
    with pytest.raises(ValueError, match="must both be set"):
        ParsedSection(text="Incomplete pages", page_start=1)


@pytest.mark.base
@pytest.mark.pipeline
def test_parsed_document_rejects_page_beyond_document() -> None:
    payload = _document().model_dump()
    payload["sections"][0]["page_end"] = 3

    with pytest.raises(ValueError, match="exceeds page_count"):
        ParsedDocument.model_validate(payload)
