"""Milestone 1 mock summary derivation; replaced by real generation in M2."""

import re

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_TLDR_SENTENCES = 2


def mock_tldr(abstract: str) -> str:
    """Return a deterministic TL;DR: the first sentences of the abstract."""
    normalized = " ".join(abstract.split())
    sentences = _SENTENCE_BOUNDARY.split(normalized)
    return " ".join(sentences[:_TLDR_SENTENCES]).strip()
