"""Blocking PDF text and layout extraction helpers."""

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import cast

import pdfplumber
import pymupdf

from mneme.services.documents.types import ParsedSection

_WHITESPACE = re.compile(r"\s+")
_UNSAFE_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]+")
_STRUCTURED_HEADING = re.compile(r"^(?:\d+(?:\.\d+)*[.)]?|[IVXLCDM]+[.)]|[A-Z][.)])\s+\S+")
_NAMED_HEADING = re.compile(
    r"^(?:\d+(?:\.\d+)*[.)]?\s+)?(?:abstract|introduction|background|related work|"
    r"methods?|methodology|approach|experiments?|results?|discussion|limitations?|"
    r"conclusions?|references|acknowledg(?:e)?ments?|appendix)\b",
    re.IGNORECASE,
)
_LINE_Y_TOLERANCE = 2.5
_COLUMN_GUTTER_RATIO = 0.02
_SPANNING_BLOCK_RATIO = 0.15
_MIN_COLUMN_TEXT = 100
_SMALL_CAPS_TOKEN = re.compile(r"^[A-Z]$")
_UPPERCASE_TOKEN = re.compile(r"^[A-Z]+$")


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


@dataclass(frozen=True, slots=True)
class _TextBlock:
    """One text block with geometry used to recover page reading order."""

    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    block_number: int


def extract_text(source_path: Path) -> TextExtraction:
    """Extract layout-aware text with PyMuPDF and classify unreadable inputs."""
    try:
        with pymupdf.open(source_path) as document:
            page_count = document.page_count
            if document.needs_pass:
                return TextExtraction([], page_count, "pdf_encrypted")
            pages = [_extract_page_text(page) for page in document]
    except Exception:
        return TextExtraction([], 0, "pdf_unreadable")
    return TextExtraction(pages, page_count)


def _extract_page_text(page: pymupdf.Page) -> str:
    """Recover a page in column reading order while retaining block boundaries."""
    raw_blocks = cast(
        list[tuple[float, float, float, float, str, int, int]],
        page.get_text("blocks", sort=False),
    )
    raw_words = cast(
        list[tuple[float, float, float, float, str, int, int, int]],
        page.get_text("words", sort=False),
    )
    words_by_block: dict[int, list[tuple[float, float, float, float, str]]] = defaultdict(list)
    for x0, y0, x1, y1, text, block_number, _line_number, _word_number in raw_words:
        words_by_block[block_number].append((x0, y0, x1, y1, text))

    blocks: list[_TextBlock] = []
    for x0, y0, x1, y1, raw_text, block_number, block_type in raw_blocks:
        if block_type != 0:
            continue
        text = _reconstruct_block_text(words_by_block.get(block_number, []))
        if not text:
            text = normalize_line(raw_text)
        if text:
            blocks.append(_TextBlock(x0, y0, x1, y1, text, block_number))

    ordered = _order_page_blocks(
        blocks,
        page_width=float(page.rect.width),
        page_height=float(page.rect.height),
    )
    return "\n\n".join(block.text for block in ordered)


def _reconstruct_block_text(
    words: list[tuple[float, float, float, float, str]],
) -> str:
    """Join physical lines in a block and undo line-wrap hyphenation."""
    if not words:
        return ""

    lines: list[list[tuple[float, float, float, float, str]]] = []
    line_tops: list[float] = []
    for word in sorted(words, key=lambda item: (item[1], item[0])):
        matching_line = next(
            (
                index
                for index, top in enumerate(line_tops)
                if abs(word[1] - top) <= _LINE_Y_TOLERANCE
            ),
            None,
        )
        if matching_line is None:
            lines.append([word])
            line_tops.append(word[1])
        else:
            lines[matching_line].append(word)

    normalized_lines = [
        normalize_line(" ".join(word[4] for word in sorted(line, key=lambda item: item[0])))
        for _top, line in sorted(
            zip(line_tops, lines, strict=True),
            key=lambda item: item[0],
        )
    ]
    joined = ""
    for line in normalized_lines:
        if not line:
            continue
        if joined.endswith("-") and line[0].islower():
            joined = joined[:-1] + line
        elif joined:
            joined += " " + line
        else:
            joined = line
    return joined


def _order_page_blocks(
    blocks: list[_TextBlock], *, page_width: float, page_height: float
) -> list[_TextBlock]:
    """Order text blocks for single- or two-column scientific layouts."""
    if not blocks:
        return []

    blocks = [
        block
        for block in blocks
        if not (
            block.x1 - block.x0 <= page_width * 0.08 and block.y1 - block.y0 >= page_height * 0.25
        )
    ]
    center = page_width / 2
    gutter = page_width * _COLUMN_GUTTER_RATIO

    def region(block: _TextBlock) -> str:
        width = block.x1 - block.x0
        crosses_center = block.x0 < center - gutter and block.x1 > center + gutter
        if crosses_center and width >= page_width * _SPANNING_BLOCK_RATIO:
            return "spanning"
        return "left" if (block.x0 + block.x1) / 2 < center else "right"

    regions = {block.block_number: region(block) for block in blocks}
    left_text = sum(len(block.text) for block in blocks if regions[block.block_number] == "left")
    right_text = sum(len(block.text) for block in blocks if regions[block.block_number] == "right")
    if left_text < _MIN_COLUMN_TEXT or right_text < _MIN_COLUMN_TEXT:
        return sorted(blocks, key=lambda block: (block.y0, block.x0, block.block_number))

    spanning = sorted(
        (block for block in blocks if regions[block.block_number] == "spanning"),
        key=lambda block: (block.y0, block.x0, block.block_number),
    )
    column_blocks = [block for block in blocks if regions[block.block_number] != "spanning"]

    def order_columns(items: list[_TextBlock]) -> list[_TextBlock]:
        left = sorted(
            (item for item in items if regions[item.block_number] == "left"),
            key=lambda item: (item.y0, item.x0, item.block_number),
        )
        right = sorted(
            (item for item in items if regions[item.block_number] == "right"),
            key=lambda item: (item.y0, item.x0, item.block_number),
        )
        return [*left, *right]

    ordered: list[_TextBlock] = []
    remaining = list(column_blocks)
    for block in spanning:
        before = [item for item in remaining if item.y1 <= block.y0 + _LINE_Y_TOLERANCE]
        if before:
            ordered.extend(order_columns(before))
            before_ids = {item.block_number for item in before}
            remaining = [item for item in remaining if item.block_number not in before_ids]
        ordered.append(block)
    ordered.extend(order_columns(remaining))
    return ordered


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
            lines.extend(_group_words(page_number, words, page_width=float(page.width)))

    positive_sizes = [size for size in character_sizes if size > 0]
    if not positive_sizes:
        return {}
    body_size = median(positive_sizes)
    headings: dict[int, dict[str, str]] = {}
    for line in lines:
        if _looks_like_heading(line, body_size):
            headings.setdefault(line.page_number, {})[_heading_key(line.text)] = line.text
    return headings


def _group_words(
    page_number: int,
    words: list[dict[str, object]],
    *,
    page_width: float | None = None,
) -> list[LayoutLine]:
    rows: list[list[dict[str, object]]] = []
    for word in sorted(
        words, key=lambda item: (_as_float(item.get("top")), _as_float(item.get("x0")))
    ):
        if not rows or abs(_as_float(word.get("top")) - _as_float(rows[-1][0].get("top"))) > 2.0:
            rows.append([word])
        else:
            rows[-1].append(word)

    grouped: list[list[dict[str, object]]] = []
    for row in rows:
        current: list[dict[str, object]] = []
        previous_x1: float | None = None
        center = page_width / 2 if page_width is not None else None
        for word in sorted(row, key=lambda item: _as_float(item.get("x0"))):
            x0 = _as_float(word.get("x0"))
            font_size = _as_float(word.get("size"))
            crosses_column_gutter = (
                center is not None
                and previous_x1 is not None
                and previous_x1 < center - 4.0
                and x0 > center + 4.0
            )
            if (
                current
                and previous_x1 is not None
                and (crosses_column_gutter or x0 - previous_x1 > max(24.0, font_size * 2.5))
            ):
                grouped.append(current)
                current = []
            current.append(word)
            previous_x1 = _as_float(word.get("x1"))
        if current:
            grouped.append(current)

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
    canonical = _collapse_split_small_caps(line.text)
    words = canonical.split()
    if not 1 <= len(words) <= 18 or len(canonical) > 180:
        return False
    if not any(character.isalpha() for character in canonical):
        return False
    elevated = line.font_size >= max(body_size + 1.5, body_size * 1.12)
    very_elevated = line.font_size >= body_size * 1.3
    normal_sized = line.font_size >= body_size * 0.9
    structured = bool(_STRUCTURED_HEADING.match(canonical))
    named = bool(_NAMED_HEADING.match(canonical))
    title_like = _looks_title_like(canonical)
    sentence_like = canonical.endswith((".", ",", ";", "?", "!"))
    return (
        (structured and normal_sized and title_like and not sentence_like)
        or (named and normal_sized and (elevated or line.bold or title_like) and not sentence_like)
        or (very_elevated and title_like and not sentence_like)
        or (elevated and line.bold and not sentence_like)
    )


def _looks_title_like(text: str) -> bool:
    """Return whether most lexical words look like a compact title."""
    if len(text.strip()) < 3:
        return False
    words = [word.strip("()[]{}:;,.\u2014-") for word in text.split()]
    lexical = [word for word in words if any(character.isalpha() for character in word)]
    if not lexical:
        return False
    titled = sum(word[0].isupper() for word in lexical if word)
    return titled / len(lexical) >= 0.6


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
        text = _join_paragraphs(content)
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
                if content and content[-1]:
                    content.append("")
                continue
            heading = page_headings.get(_heading_key(normalized))
            if heading is not None:
                flush()
                title = normalized
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


def _join_paragraphs(lines: list[str]) -> str:
    """Normalize section lines while retaining parser block boundaries."""
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if line:
            current.append(line)
        elif current:
            paragraphs.append(normalize_line(" ".join(current)))
            current = []
    if current:
        paragraphs.append(normalize_line(" ".join(current)))
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


def normalize_page(text: str) -> str:
    """Normalize extracted page text while preserving paragraph boundaries."""
    paragraphs = re.split(r"\n\s*\n", text)
    return "\n\n".join(
        normalized for paragraph in paragraphs if (normalized := normalize_line(paragraph))
    )


def normalize_line(text: str) -> str:
    """Collapse unsafe or repeated whitespace in extracted text."""
    sanitized = _UNSAFE_CONTROL_CHARACTERS.sub(" ", text)
    return _WHITESPACE.sub(" ", sanitized).strip()


def _heading_key(text: str) -> str:
    return _collapse_split_small_caps(text).casefold()


def _collapse_split_small_caps(text: str) -> str:
    """Join words split by PDF small-caps extraction (for example, R ESULTS)."""
    tokens = normalize_line(text).split()
    collapsed: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if (
            index + 1 < len(tokens)
            and _SMALL_CAPS_TOKEN.fullmatch(token) is not None
            and _UPPERCASE_TOKEN.fullmatch(tokens[index + 1]) is not None
            and len(tokens[index + 1]) >= 2
        ):
            collapsed.append(token + tokens[index + 1])
            index += 2
            continue
        collapsed.append(token)
        index += 1
    return " ".join(collapsed)


def text_size(text: str) -> int:
    """Count non-whitespace characters for quality-tier selection."""
    return len(_WHITESPACE.sub("", text))


def _as_float(value: object) -> float:
    try:
        return float(cast(float | int | str, value))
    except (TypeError, ValueError):
        return 0.0
