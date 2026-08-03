"""Deterministic claim-to-chunk provenance for structured summaries.

Provenance is computed after generation by lexical matching against the
persisted chunks of the exact summarized revision. The model never produces
or influences a source reference: a generated claim can be wrong, but its
provenance cannot be invented. Claims whose content words do not overlap
any stored chunk strongly enough are marked unmatched instead of receiving
a guessed source.
"""

import re
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mneme.ai.qa import content_words
from mneme.models.artifact import SourceMatchStatus

CLAIM_MATCH_VERSION = "claim-match-v1"
CLAIM_MATCH_MIN_OVERLAP = 0.3
EXCERPT_MAX_CHARS = 300

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


class ChunkSource(Protocol):
    """The chunk surface provenance matching needs; satisfied by PaperChunk."""

    id: UUID
    chunk_index: int
    section_title: str | None
    content: str
    page_start: int | None
    page_end: int | None


class ClaimSource(BaseModel):
    """One verifiable source reference into an exact revision's chunk."""

    model_config = ConfigDict(frozen=True)

    chunk_id: UUID
    chunk_index: int = Field(ge=0)
    section_title: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    excerpt: str = Field(min_length=1, max_length=EXCERPT_MAX_CHARS)


class SummaryClaim(BaseModel):
    """A generated claim with its matched source or an explicit unmatched state."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1)
    matched: bool
    source: ClaimSource | None = None
    match_version: str = CLAIM_MATCH_VERSION

    @model_validator(mode="after")
    def _source_iff_matched(self) -> "SummaryClaim":
        if self.matched != (self.source is not None):
            raise ValueError("a claim is matched exactly when it carries a source")
        return self


def _claim_overlap(claim_words: set[str], chunk_words: set[str]) -> float:
    if not claim_words:
        return 0.0
    return len(claim_words & chunk_words) / len(claim_words)


def _best_excerpt(claim_words: set[str], content: str) -> str:
    """Pick the chunk sentence sharing the most content words with the claim.

    Ties break on sentence order, so the excerpt is deterministic for
    identical inputs. The excerpt is always literal chunk text.
    """
    sentences = [part.strip() for part in _SENTENCE_BOUNDARY.split(content) if part.strip()]
    if not sentences:
        sentences = [content.strip()]
    best = max(
        enumerate(sentences),
        key=lambda item: (_claim_overlap(claim_words, content_words(item[1])), -item[0]),
    )[1]
    return best[:EXCERPT_MAX_CHARS]


def match_claims(claims: Sequence[str], chunks: Sequence[ChunkSource]) -> tuple[SummaryClaim, ...]:
    """Match each claim to its best supporting chunk of the same revision.

    A claim is matched when at least ``CLAIM_MATCH_MIN_OVERLAP`` of its
    content words appear in one chunk; the best-overlapping chunk wins and
    ties break on the lowest chunk index. Claims below the threshold are
    returned unmatched with no source.
    """
    ordered = sorted(chunks, key=lambda chunk: chunk.chunk_index)
    results: list[SummaryClaim] = []
    for claim in claims:
        claim_words = content_words(claim)
        best_chunk: ChunkSource | None = None
        best_overlap = 0.0
        for chunk in ordered:
            overlap = _claim_overlap(claim_words, content_words(chunk.content))
            if overlap > best_overlap:
                best_chunk = chunk
                best_overlap = overlap
        if best_chunk is None or best_overlap < CLAIM_MATCH_MIN_OVERLAP:
            results.append(SummaryClaim(text=claim, matched=False))
            continue
        results.append(
            SummaryClaim(
                text=claim,
                matched=True,
                source=ClaimSource(
                    chunk_id=best_chunk.id,
                    chunk_index=best_chunk.chunk_index,
                    section_title=best_chunk.section_title,
                    page_start=best_chunk.page_start,
                    page_end=best_chunk.page_end,
                    excerpt=_best_excerpt(claim_words, best_chunk.content),
                ),
            )
        )
    return tuple(results)


def provenance_status(claims: Sequence[SummaryClaim]) -> SourceMatchStatus:
    """Aggregate per-claim results into the stored summary-level status."""
    if not claims:
        return SourceMatchStatus.NOT_CHECKED
    matched = sum(1 for claim in claims if claim.matched)
    if matched == len(claims):
        return SourceMatchStatus.MATCHED
    if matched:
        return SourceMatchStatus.PARTIAL
    return SourceMatchStatus.UNMATCHED
