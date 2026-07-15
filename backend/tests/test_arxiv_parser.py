"""Tests for safe arXiv Atom parsing."""

from pathlib import Path

import pytest

from mneme.services.arxiv import ArxivAPIError, ArxivParseError, parse_arxiv_feed

FIXTURES = Path(__file__).parent / "fixtures" / "arxiv"


@pytest.mark.pipeline
def test_parse_category_feed() -> None:
    feed = parse_arxiv_feed((FIXTURES / "category_feed.xml").read_bytes())
    modern, legacy = feed.records

    assert (feed.total_results, feed.start_index, feed.items_per_page) == (2, 0, 2)
    assert modern.arxiv_id == "2501.12345"
    assert modern.version_number == 2
    assert modern.title == "A Multiline Research Title"
    assert modern.abstract == "First line. Second line."
    assert modern.authors[0].name == "Jos\u00e9 Example"
    assert modern.authors[0].affiliation == "Mneme Lab"
    assert modern.categories == ("cs.AI", "cs.CL")
    assert modern.abstract_url == "https://arxiv.org/abs/2501.12345v2"
    assert modern.pdf_url == "https://arxiv.org/pdf/2501.12345v2"
    assert legacy.arxiv_id == "hep-ex/0307015"
    assert legacy.version_number == 1
    assert legacy.source_license is None


@pytest.mark.pipeline
def test_empty_feed_is_valid() -> None:
    feed = parse_arxiv_feed((FIXTURES / "empty_feed.xml").read_bytes())

    assert feed.records == ()
    assert feed.total_results == 0


@pytest.mark.pipeline
def test_atom_api_error_is_not_a_paper() -> None:
    with pytest.raises(ArxivAPIError, match="Incorrect ID format"):
        parse_arxiv_feed((FIXTURES / "api_error.xml").read_bytes())


@pytest.mark.pipeline
@pytest.mark.parametrize(
    "content",
    [
        "<feed>",
        '<!DOCTYPE feed [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><feed>&xxe;</feed>',
    ],
)
def test_malformed_or_unsafe_xml_is_rejected(content: str) -> None:
    with pytest.raises(ArxivParseError, match="Invalid or unsafe"):
        parse_arxiv_feed(content)


@pytest.mark.pipeline
def test_mismatched_revision_links_are_rejected() -> None:
    content = (
        (FIXTURES / "category_feed.xml")
        .read_text()
        .replace("pdf/2501.12345v2", "pdf/2501.12345v3", 1)
    )

    with pytest.raises(ArxivParseError, match="different revisions"):
        parse_arxiv_feed(content)
