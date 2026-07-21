"""Section-aware chunking of parsed paper text.

Input is the parse stage's section list (title, text, page range); output is
an ordered list of chunk drafts ready for persistence as ``paper_chunks``
rows. Chunking is deterministic: the same sections always produce the same
chunks and content hashes, which keeps the embed stage idempotent.
"""

import hashlib
import re

from pydantic import BaseModel, ConfigDict, Field

from mneme.services.documents import ParsedSection

_WHITESPACE = re.compile(r"\s+")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")

# Rough words-per-token ratio for scientific English; used only for sizing,
# never for billing, so a conservative estimate is fine.
_WORDS_PER_TOKEN = 0.75


class ChunkDraft(BaseModel):
    """A chunk ready to persist, mirroring the ``paper_chunks`` columns."""

    model_config = ConfigDict(frozen=True)

    chunk_index: int = Field(ge=0)
    section_title: str | None
    content: str
    content_hash: str
    token_count: int = Field(ge=0)
    page_start: int | None = None
    page_end: int | None = None


def estimate_tokens(text: str) -> int:
    """Approximate the token count of a text from its word count."""
    words = len(text.split())
    return int(words / _WORDS_PER_TOKEN) if words else 0


def _sentences(text: str) -> list[str]:
    normalized = _WHITESPACE.sub(" ", text).strip()
    return [sentence for sentence in _SENTENCE_BOUNDARY.split(normalized) if sentence]


def _split_section(text: str, *, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Split one section into pieces of at most ``max_tokens`` with overlap.

    Splits at sentence boundaries; a single sentence longer than the limit is
    kept whole rather than broken mid-formula.
    """
    sentences = _sentences(text)
    if not sentences:
        return []

    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in sentences:
        sentence_tokens = estimate_tokens(sentence)
        if current and current_tokens + sentence_tokens > max_tokens:
            pieces.append(" ".join(current))
            overlap: list[str] = []
            overlap_size = 0
            for previous in reversed(current):
                previous_tokens = estimate_tokens(previous)
                if overlap_size + previous_tokens > overlap_tokens:
                    break
                overlap.insert(0, previous)
                overlap_size += previous_tokens
            current = overlap
            current_tokens = overlap_size
        current.append(sentence)
        current_tokens += sentence_tokens
    if current:
        pieces.append(" ".join(current))
    return pieces


def chunk_sections(
    sections: list[ParsedSection],
    *,
    max_tokens: int,
    overlap_tokens: int,
) -> list[ChunkDraft]:
    """Chunk parsed sections, preserving section titles and page ranges."""
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")

    drafts: list[ChunkDraft] = []
    for section in sections:
        for piece in _split_section(
            section.text, max_tokens=max_tokens, overlap_tokens=overlap_tokens
        ):
            drafts.append(
                ChunkDraft(
                    chunk_index=len(drafts),
                    section_title=section.title,
                    content=piece,
                    content_hash=hashlib.sha256(piece.encode("utf-8")).hexdigest(),
                    token_count=estimate_tokens(piece),
                    page_start=section.page_start,
                    page_end=section.page_end,
                )
            )
    return drafts
