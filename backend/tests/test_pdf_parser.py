"""PDF text extraction, structure detection, and safe fallbacks."""

import inspect
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pymupdf
import pytest

from mneme.models.paper import ParseQuality
from mneme.services.documents import PdfParseError, PdfParser
from mneme.services.documents.parser_layout import normalize_line

PAPER_ID = UUID("11111111-1111-4111-8111-111111111111")
VERSION_ID = UUID("22222222-2222-4222-8222-222222222222")
CHECKSUM = "a" * 64
PARSED_AT = datetime(2026, 7, 21, tzinfo=UTC)
ABSTRACT = "The abstract remains available when PDF extraction cannot produce useful text."


def _write_pdf(path: Path, pages: list[list[tuple[str, float]]], *, password: str = "") -> None:
    document = pymupdf.open()
    for lines in pages:
        page = document.new_page()
        y = 72.0
        for text, font_size in lines:
            page.insert_text((72.0, y), text, fontsize=font_size)
            y += max(24.0, font_size * 1.8)
    if password:
        document.save(
            path,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,  # pyrefly: ignore [missing-attribute]
            owner_pw="owner-password",
            user_pw=password,
        )
    else:
        document.save(path)
    document.close()


def _write_two_column_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page()
    right_body = (
        "The right column reports evaluation results after the complete left column. "
        "Its insertion order deliberately comes first in the PDF content stream."
    )
    left_body = (
        "The left column introduces the problem and method before any reported results. "
        "The parser must keep this logical reading order."
    )

    # Insert the right column first to ensure extraction does not trust content-stream order.
    page.insert_text((340, 90), "II. Results", fontsize=14)
    page.insert_textbox(pymupdf.Rect(340, 110, 550, 220), right_body, fontsize=11)
    page.insert_text((60, 90), "I. Introduction", fontsize=14)
    page.insert_textbox(pymupdf.Rect(60, 110, 270, 220), left_body, fontsize=11)
    page.insert_text((190, 50), "A Layout-Aware Study", fontsize=18)
    document.save(path)
    document.close()


def _parse(path: Path, *, min_text_chars: int = 20, abstract: str = ABSTRACT):
    return PdfParser(min_text_chars=min_text_chars).parse(
        path,
        paper_id=PAPER_ID,
        paper_version_id=VERSION_ID,
        source_checksum=CHECKSUM,
        abstract=abstract,
        parsed_at=PARSED_AT,
    )


@pytest.mark.base
@pytest.mark.pipeline
def test_detects_structured_sections_with_page_ranges(tmp_path: Path) -> None:
    path = tmp_path / "structured.pdf"
    _write_pdf(
        path,
        [
            [
                ("1 Introduction", 18),
                ("This introduction explains the research problem and motivation.", 11),
            ],
            [
                ("2 Methods", 18),
                ("The method combines retrieval with a controlled evaluation protocol.", 11),
            ],
        ],
    )

    parsed = _parse(path)

    assert parsed.parse_quality is ParseQuality.STRUCTURED
    assert parsed.page_count == 2
    assert [section.title for section in parsed.sections] == ["1 Introduction", "2 Methods"]
    assert [(section.page_start, section.page_end) for section in parsed.sections] == [
        (1, 1),
        (2, 2),
    ]
    assert "research problem" in parsed.sections[0].text
    assert "controlled evaluation" in parsed.sections[1].text
    assert parsed.fallback_reason is None


@pytest.mark.base
@pytest.mark.pipeline
def test_uses_text_only_tier_when_headings_are_not_detected(tmp_path: Path) -> None:
    path = tmp_path / "plain.pdf"
    _write_pdf(
        path,
        [
            [("All lines use the same body font and contain enough extractable text.", 11)],
            [("The second page continues the paper without a section heading.", 11)],
        ],
    )

    parsed = _parse(path)

    assert parsed.parse_quality is ParseQuality.TEXT_ONLY
    assert len(parsed.sections) == 1
    assert parsed.sections[0].title is None
    assert parsed.sections[0].page_start == 1
    assert parsed.sections[0].page_end == 2
    assert "second page" in parsed.sections[0].text
    assert parsed.fallback_reason == "section_headings_not_detected"


@pytest.mark.base
@pytest.mark.pipeline
def test_recovers_two_column_reading_order_from_layout(tmp_path: Path) -> None:
    path = tmp_path / "two-column.pdf"
    _write_two_column_pdf(path)

    parsed = _parse(path)

    titles = [section.title for section in parsed.sections]
    introduction = titles.index("I. Introduction")
    results = titles.index("II. Results")
    assert introduction < results
    assert "introduces the problem" in parsed.sections[introduction].text
    assert "reports evaluation results" in parsed.sections[results].text
    assert "insertion order deliberately comes first" not in parsed.sections[introduction].text


@pytest.mark.base
@pytest.mark.pipeline
def test_blank_pdf_falls_back_to_normalized_abstract(tmp_path: Path) -> None:
    path = tmp_path / "blank.pdf"
    _write_pdf(path, [[]])

    parsed = _parse(path, abstract="  A fallback\n abstract with   stable spacing.  ")

    assert parsed.parse_quality is ParseQuality.ABSTRACT_ONLY
    assert parsed.page_count == 1
    assert parsed.sections[0].title == "Abstract"
    assert parsed.sections[0].text == "A fallback abstract with stable spacing."
    assert parsed.sections[0].page_start is None
    assert parsed.fallback_reason == "insufficient_text"


@pytest.mark.base
@pytest.mark.pipeline
def test_encrypted_pdf_falls_back_without_attempting_password_recovery(tmp_path: Path) -> None:
    path = tmp_path / "encrypted.pdf"
    _write_pdf(path, [[("Protected paper text", 11)]], password="secret")

    parsed = _parse(path)

    assert parsed.parse_quality is ParseQuality.ABSTRACT_ONLY
    assert parsed.fallback_reason == "pdf_encrypted"
    assert parsed.sections[0].text == ABSTRACT


@pytest.mark.base
@pytest.mark.pipeline
def test_unreadable_pdf_without_abstract_reports_safe_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not a PDF")

    with pytest.raises(PdfParseError, match="no abstract fallback") as error:
        _parse(path, abstract="   ")

    assert error.value.code == "abstract_unavailable"


@pytest.mark.base
@pytest.mark.pipeline
def test_parser_contract_is_synchronous() -> None:
    assert not inspect.iscoroutinefunction(PdfParser.parse)


@pytest.mark.base
@pytest.mark.pipeline
def test_normalization_removes_database_unsafe_control_characters() -> None:
    assert normalize_line("alpha\x00beta\x1f gamma\t delta") == "alpha beta gamma delta"
