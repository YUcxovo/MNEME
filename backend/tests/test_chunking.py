"""Section-aware chunking behavior."""

from itertools import pairwise

import pytest

from mneme.ai.chunking import ChunkDraft, ParsedSection, chunk_sections, estimate_tokens


def _section(text: str, *, title: str | None = "Introduction", pages: tuple[int, int] = (1, 2)):
    return ParsedSection(title=title, text=text, page_start=pages[0], page_end=pages[1])


@pytest.mark.base
@pytest.mark.pipeline
def test_small_section_stays_one_chunk_with_metadata() -> None:
    sections = [_section("A short paragraph. It easily fits in one chunk.")]

    drafts = chunk_sections(sections, max_tokens=200, overlap_tokens=20)

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.chunk_index == 0
    assert draft.section_title == "Introduction"
    assert draft.page_start == 1
    assert draft.page_end == 2
    assert draft.token_count > 0
    assert len(draft.content_hash) == 64


@pytest.mark.base
@pytest.mark.pipeline
def test_oversized_section_splits_with_overlap() -> None:
    sentences = [f"Sentence number {index} adds several more words here." for index in range(40)]
    sections = [_section(" ".join(sentences))]

    drafts = chunk_sections(sections, max_tokens=60, overlap_tokens=15)

    assert len(drafts) > 1
    assert [draft.chunk_index for draft in drafts] == list(range(len(drafts)))
    assert all(draft.section_title == "Introduction" for draft in drafts)
    for previous, current in pairwise(drafts):
        overlap_head = current.content[:30]
        assert overlap_head in previous.content, "consecutive chunks should overlap"


@pytest.mark.base
@pytest.mark.pipeline
def test_chunk_indexes_continue_across_sections() -> None:
    sections = [
        _section("First section text. More words here.", title="Intro"),
        _section("Second section text. Even more words.", title="Method"),
    ]

    drafts = chunk_sections(sections, max_tokens=200, overlap_tokens=20)

    assert [draft.chunk_index for draft in drafts] == [0, 1]
    assert drafts[0].section_title == "Intro"
    assert drafts[1].section_title == "Method"


@pytest.mark.base
@pytest.mark.pipeline
def test_chunking_is_deterministic() -> None:
    sections = [_section("Deterministic input text. Same every time. No randomness involved.")]

    first = chunk_sections(sections, max_tokens=100, overlap_tokens=10)
    second = chunk_sections(sections, max_tokens=100, overlap_tokens=10)

    assert first == second


@pytest.mark.base
@pytest.mark.pipeline
def test_single_sentence_longer_than_limit_is_kept_whole() -> None:
    long_sentence = "word " * 300
    sections = [_section(long_sentence.strip() + ".")]

    drafts = chunk_sections(sections, max_tokens=50, overlap_tokens=5)

    assert len(drafts) == 1
    assert isinstance(drafts[0], ChunkDraft)


@pytest.mark.base
@pytest.mark.pipeline
def test_overlap_must_be_smaller_than_max_tokens() -> None:
    with pytest.raises(ValueError):
        chunk_sections([_section("Some text.")], max_tokens=50, overlap_tokens=50)


@pytest.mark.base
def test_token_estimate_scales_with_words() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("one two three") == 4  # 3 words / 0.75
