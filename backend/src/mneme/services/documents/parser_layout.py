"""Blocking PDF text and layout extraction helpers."""

import re
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import cast

import pdfplumber
import pymupdf

from mneme.services.documents.types import ParsedSection

_WHITESPACE = re.compile(r"\s+")
_NUMBERED_HEADING = re.compile(r"^\d+(?:\.\d+)*[.)]?\s+\S+")
_NAMED_HEADING = re.compile(
    r"^(?:\d+(?:\.\d+)*[.)]?\s+)?(?:abstract|introduction|background|related work|"
    r"methods?|methodology|approach|experiments?|results?|discussion|limitations?|"
    r"conclusions?|references|acknowledg(?:e)?ments?|appendix)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class LayoutLine:
    """One normalized layout line used for heading detection."""

    page_number: int
    text: str
    font_size: float
    bold: bool


@dataclass(frozen=True, slots=True)
class TextExtraction:
    """Page text plus a safe failure reason when extraction is unusable."""

    pages: list[str]
    page_count: int
    failure_reason: str | None = None


def extract_text(source_path: Path) -> TextExtraction:
    """Extract normalized text with PyMuPDF and classify unreadable inputs."""
    try:
        with pymupdf.open(source_path) as document:
            page_count = document.page_count
            if document.needs_pass:
                return TextExtraction([], page_count, "pdf_encrypted")
            pages = [
                normalize_page(cast(str, page.get_text("text", sort=True))) for page in document
            ]
    except Exception:
        return TextExtraction([], 0, "pdf_unreadable")
    return TextExtraction(pages, page_count)


def extract_headings(source_path: Path) -> dict[int, dict[str, str]]:
    """Detect likely section headings from pdfplumber layout metadata."""
    with pdfplumber.open(source_path) as document:
        lines: list[LayoutLine] = []
        character_sizes: list[float] = []
        for page_number, page in enumerate(document.pages, start=1):
            characters = cast(list[dict[str, object]], page.chars)
            character_sizes.extend(_as_float(char.get("size")) for char in characters)
            words = cast(
                list[dict[str, object]],
                page.extract_words(
                    extra_attrs=["fontname", "size"],
                    keep_blank_chars=False,
                    use_text_flow=False,
                ),
            )
            lines.extend(_group_words(page_number, words))

    positive_sizes = [size for size in character_sizes if size > 0]
    if not positive_sizes:
        return {}
    body_size = median(positive_sizes)
    headings: dict[int, dict[str, str]] = {}
    for line in lines:
        if _looks_like_heading(line, body_size):
            headings.setdefault(line.page_number, {})[_heading_key(line.text)] = line.text
    return headings


def _group_words(page_number: int, words: list[dict[str, object]]) -> list[LayoutLine]:
    grouped: list[list[dict[str, object]]] = []
    for word in sorted(
        words, key=lambda item: (_as_float(item.get("top")), _as_float(item.get("x0")))
    ):
        if (
            not grouped
            or abs(_as_float(word.get("top")) - _as_float(grouped[-1][0].get("top"))) > 2.0
        ):
            grouped.append([word])
        else:
            grouped[-1].append(word)

    lines: list[LayoutLine] = []
    for words_on_line in grouped:
        text = normalize_line(" ".join(str(word.get("text", "")) for word in words_on_line))
        if not text:
            continue
        font_names = [str(word.get("fontname", "")).casefold() for word in words_on_line]
        lines.append(
            LayoutLine(
                page_number=page_number,
                text=text,
                font_size=max(_as_float(word.get("size")) for word in words_on_line),
                bold=any("bold" in name for name in font_names),
            )
        )
    return lines


def _looks_like_heading(line: LayoutLine, body_size: float) -> bool:
    words = line.text.split()
    if not 1 <= len(words) <= 18 or len(line.text) > 180:
        return False
    if not any(character.isalpha() for character in line.text):
        return False
    elevated = line.font_size >= max(body_size + 1.5, body_size * 1.12)
    explicit = bool(_NAMED_HEADING.match(line.text) or _NUMBERED_HEADING.match(line.text))
    sentence_like = line.text.endswith((".", ",", ";", "?", "!"))
    return (explicit and (elevated or line.bold)) or (elevated and line.bold and not sentence_like)


def split_at_headings(pages: list[str], headings: dict[int, dict[str, str]]) -> list[ParsedSection]:
    """Split page text at headings that are present in extracted text."""
    if not headings:
        return []

    sections: list[ParsedSection] = []
    title: str | None = None
    content: list[str] = []
    page_start: int | None = None
    page_end: int | None = None
    found_heading = False

    def flush() -> None:
        nonlocal content, page_start, page_end
        text = normalize_line(" ".join(content))
        if text and page_start is not None and page_end is not None:
            sections.append(
                ParsedSection(
                    title=title,
                    text=text,
                    page_start=page_start,
                    page_end=page_end,
                )
            )
        content = []
        page_start = None
        page_end = None

    for page_number, page_text in enumerate(pages, start=1):
        page_headings = headings.get(page_number, {})
        for line in page_text.splitlines():
            normalized = normalize_line(line)
            if not normalized:
                continue
            heading = page_headings.get(_heading_key(normalized))
            if heading is not None:
                flush()
                title = heading
                page_start = page_number
                page_end = page_number
                found_heading = True
                continue
            if page_start is None:
                page_start = page_number
            page_end = page_number
            content.append(normalized)
    flush()
    return sections if found_heading else []


def normalize_page(text: str) -> str:
    """Normalize extracted page text while preserving line boundaries."""
    return "\n".join(
        normalized
        for line in text.replace("\x00", "").splitlines()
        if (normalized := normalize_line(line))
    )


def normalize_line(text: str) -> str:
    """Collapse unsafe or repeated whitespace in extracted text."""
    return _WHITESPACE.sub(" ", text).strip()


def _heading_key(text: str) -> str:
    return normalize_line(text).casefold()


def text_size(text: str) -> int:
    """Count non-whitespace characters for quality-tier selection."""
    return len(_WHITESPACE.sub("", text))


def _as_float(value: object) -> float:
    try:
        return float(cast(float | int | str, value))
    except (TypeError, ValueError):
        return 0.0
