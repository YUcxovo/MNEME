"""Safe parsing and normalization for arXiv Atom responses."""

import re
from datetime import UTC, datetime
from urllib.parse import urlparse
from xml.etree.ElementTree import Element

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from mneme.services.arxiv.types import ArxivAuthorRecord, ArxivFeed, ArxivPaperRecord

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"
OPENSEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"
VERSIONED_ID = re.compile(r"(?P<base>(?:\d{4}\.\d{4,5}|[^/]+/\d{7}))v(?P<version>[1-9]\d*)$")


class ArxivParseError(ValueError):
    """The response was not a valid arXiv result feed."""


class ArxivAPIError(ArxivParseError):
    """arXiv encoded an API query error inside an Atom feed."""


def _text(parent: Element, path: str, *, required: bool = False) -> str | None:
    node = parent.find(path)
    value = " ".join((node.text or "").split()) if node is not None else ""
    if required and not value:
        raise ArxivParseError(f"Missing required Atom field: {path}")
    return value or None


def _datetime(parent: Element, path: str) -> datetime:
    value = _text(parent, path, required=True)
    assert value is not None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArxivParseError(f"Invalid arXiv timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise ArxivParseError("arXiv timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _versioned_id(url: str) -> tuple[str, int]:
    path = urlparse(url).path.removesuffix(".pdf")
    candidate = path.removeprefix("/abs/").removeprefix("/pdf/")
    match = VERSIONED_ID.fullmatch(candidate)
    if match is None:
        raise ArxivParseError(f"Expected a versioned arXiv URL: {url}")
    return match.group("base"), int(match.group("version"))


def _links(entry: Element) -> tuple[str, int]:
    alternate = None
    pdf = None
    for link in entry.findall(f"{ATOM}link"):
        if link.get("rel") == "alternate":
            alternate = link.get("href")
        if link.get("title") == "pdf":
            pdf = link.get("href")
    if not alternate or not pdf:
        raise ArxivParseError("Entry is missing versioned abstract or PDF links")
    alternate_id = _versioned_id(alternate)
    if alternate_id != _versioned_id(pdf):
        raise ArxivParseError("Abstract and PDF links identify different revisions")
    return alternate_id


def _entry(entry: Element) -> ArxivPaperRecord:
    entry_id = _text(entry, f"{ATOM}id", required=True)
    title = _text(entry, f"{ATOM}title", required=True)
    abstract = _text(entry, f"{ATOM}summary", required=True)
    assert entry_id is not None and title is not None and abstract is not None
    if "/api/errors#" in entry_id or title.casefold() == "error":
        raise ArxivAPIError(abstract)

    arxiv_id, version = _links(entry)
    entry_base = urlparse(entry_id).path.removeprefix("/abs/")
    entry_match = VERSIONED_ID.fullmatch(entry_base)
    if entry_match is not None:
        entry_base = entry_match.group("base")
    if entry_base != arxiv_id:
        raise ArxivParseError("Entry ID and links identify different works")

    authors = tuple(
        ArxivAuthorRecord(
            name=_text(author, f"{ATOM}name", required=True) or "",
            affiliation=_text(author, f"{ARXIV}affiliation"),
        )
        for author in entry.findall(f"{ATOM}author")
    )
    categories = tuple(
        term for node in entry.findall(f"{ATOM}category") if (term := node.get("term"))
    )
    primary_node = entry.find(f"{ARXIV}primary_category")
    primary = primary_node.get("term") if primary_node is not None else None
    if not authors or not categories or not primary:
        raise ArxivParseError("Entry is missing authors or categories")

    license_node = entry.find(f"{ARXIV}license")
    source_license = license_node.get("href") if license_node is not None else None
    suffix = f"{arxiv_id}v{version}"
    return ArxivPaperRecord(
        arxiv_id=arxiv_id,
        version_number=version,
        title=title,
        abstract=abstract,
        authors=authors,
        categories=categories,
        primary_category=primary,
        published_at=_datetime(entry, f"{ATOM}published"),
        updated_at=_datetime(entry, f"{ATOM}updated"),
        abstract_url=f"https://arxiv.org/abs/{suffix}",
        pdf_url=f"https://arxiv.org/pdf/{suffix}",
        source_license=source_license,
        doi=_text(entry, f"{ARXIV}doi"),
        comment=_text(entry, f"{ARXIV}comment"),
        journal_reference=_text(entry, f"{ARXIV}journal_ref"),
    )


def _integer(root: Element, name: str, default: int) -> int:
    value = _text(root, f"{OPENSEARCH}{name}")
    try:
        return int(value) if value is not None else default
    except ValueError as exc:
        raise ArxivParseError(f"Invalid OpenSearch integer: {name}") from exc


def parse_arxiv_feed(content: bytes | str) -> ArxivFeed:
    """Parse an arXiv Atom response without allowing external XML entities."""
    try:
        root = ElementTree.fromstring(content)
        records = tuple(_entry(entry) for entry in root.findall(f"{ATOM}entry"))
    except (DefusedXmlException, ElementTree.ParseError) as exc:
        raise ArxivParseError("Invalid or unsafe Atom XML") from exc
    return ArxivFeed(
        records=records,
        total_results=_integer(root, "totalResults", len(records)),
        start_index=_integer(root, "startIndex", 0),
        items_per_page=_integer(root, "itemsPerPage", len(records)),
    )
