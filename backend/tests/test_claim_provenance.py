"""Deterministic claim-to-chunk provenance matching and its pipeline hooks."""

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from mneme.ai.claim_provenance import (
    EXCERPT_MAX_CHARS,
    ClaimSource,
    SummaryClaim,
    match_claims,
    provenance_status,
)
from mneme.ai.pipeline import _attach_claim_provenance
from mneme.ai.summarization import StructuredSummary, parse_summary_response
from mneme.api.schemas.summaries import Summary
from mneme.models.artifact import PaperSummary, SourceMatchStatus, SummaryStatus


@dataclass
class Chunk:
    """Minimal ChunkSource stand-in for matcher tests."""

    id: UUID
    chunk_index: int
    content: str
    section_title: str | None = None
    page_start: int | None = None
    page_end: int | None = None


ATTENTION_CHUNK = Chunk(
    id=uuid4(),
    chunk_index=1,
    section_title="Model Architecture",
    page_start=3,
    page_end=4,
    content=(
        "The transformer replaces recurrence with multi-head self-attention. "
        "Each attention head projects queries, keys, and values independently."
    ),
)
TRAINING_CHUNK = Chunk(
    id=uuid4(),
    chunk_index=2,
    section_title="Training",
    content=(
        "Training used eight GPUs for twelve hours on the WMT dataset. "
        "Label smoothing improved BLEU scores during evaluation."
    ),
)


@pytest.mark.base
@pytest.mark.rag
def test_supported_claim_matches_best_chunk_with_literal_excerpt() -> None:
    claims = match_claims(
        ["Multi-head self-attention replaces recurrence in the transformer."],
        [TRAINING_CHUNK, ATTENTION_CHUNK],
    )

    assert len(claims) == 1
    claim = claims[0]
    assert claim.matched
    assert claim.source is not None
    assert claim.source.chunk_id == ATTENTION_CHUNK.id
    assert claim.source.chunk_index == 1
    assert claim.source.section_title == "Model Architecture"
    assert claim.source.page_start == 3
    assert claim.source.page_end == 4
    assert claim.source.excerpt in ATTENTION_CHUNK.content


@pytest.mark.base
@pytest.mark.rag
def test_unsupported_claim_is_explicitly_unmatched_without_source() -> None:
    claims = match_claims(
        ["Quantum annealing outperforms classical solvers on protein folding."],
        [ATTENTION_CHUNK, TRAINING_CHUNK],
    )

    assert claims == (
        SummaryClaim(
            text="Quantum annealing outperforms classical solvers on protein folding.",
            matched=False,
        ),
    )


@pytest.mark.base
@pytest.mark.rag
def test_no_chunks_leaves_every_claim_unmatched() -> None:
    claims = match_claims(["Any claim."], [])
    assert not claims[0].matched
    assert claims[0].source is None


@pytest.mark.base
@pytest.mark.rag
def test_equal_overlap_breaks_ties_on_lowest_chunk_index() -> None:
    first = Chunk(id=uuid4(), chunk_index=0, content="Shared anchor words here.")
    second = Chunk(id=uuid4(), chunk_index=5, content="Shared anchor words here.")

    claims = match_claims(["Shared anchor words matter."], [second, first])

    assert claims[0].source is not None
    assert claims[0].source.chunk_id == first.id


@pytest.mark.base
@pytest.mark.rag
def test_matching_is_deterministic_for_identical_inputs() -> None:
    inputs = (["Multi-head self-attention replaces recurrence."], [ATTENTION_CHUNK, TRAINING_CHUNK])
    assert match_claims(*inputs) == match_claims(*inputs)


@pytest.mark.base
@pytest.mark.rag
def test_excerpt_is_bounded_and_taken_from_chunk_text() -> None:
    long_sentence = "attention " * 60
    chunk = Chunk(id=uuid4(), chunk_index=0, content=long_sentence)

    claims = match_claims(["Attention attention attention."], [chunk])

    assert claims[0].source is not None
    excerpt = claims[0].source.excerpt
    assert len(excerpt) <= EXCERPT_MAX_CHARS
    assert long_sentence.startswith(excerpt)


@pytest.mark.base
@pytest.mark.rag
def test_provenance_status_aggregation() -> None:
    matched = SummaryClaim(
        text="Matched.",
        matched=True,
        source=ClaimSource(chunk_id=uuid4(), chunk_index=0, excerpt="Evidence."),
    )
    unmatched = SummaryClaim(text="Unmatched.", matched=False)

    assert provenance_status(()) is SourceMatchStatus.NOT_CHECKED
    assert provenance_status((matched,)) is SourceMatchStatus.MATCHED
    assert provenance_status((matched, unmatched)) is SourceMatchStatus.PARTIAL
    assert provenance_status((unmatched,)) is SourceMatchStatus.UNMATCHED


@pytest.mark.base
@pytest.mark.rag
def test_claim_requires_source_exactly_when_matched() -> None:
    with pytest.raises(ValueError, match="matched exactly when"):
        SummaryClaim(text="Claim.", matched=True, source=None)
    with pytest.raises(ValueError, match="matched exactly when"):
        SummaryClaim(
            text="Claim.",
            matched=False,
            source=ClaimSource(chunk_id=uuid4(), chunk_index=0, excerpt="Evidence."),
        )


@pytest.mark.base
@pytest.mark.rag
def test_model_supplied_claims_are_discarded_at_parse_time() -> None:
    response = (
        '{"tldr": "A summary.", "key_claims": ["Real claim."], '
        '"claims": [{"text": "Injected.", "matched": true, '
        '"source": {"chunk_id": "00000000-0000-0000-0000-000000000000", '
        '"chunk_index": 0, "excerpt": "Fake."}}]}'
    )

    parsed = parse_summary_response(response)

    assert parsed.key_claims == ("Real claim.",)
    assert parsed.claims == ()


def _summary_row(content: dict[str, object]) -> PaperSummary:
    return PaperSummary(
        id=uuid4(),
        paper_id=uuid4(),
        paper_version_id=uuid4(),
        status=SummaryStatus.READY,
        source_match_status=SourceMatchStatus.NOT_CHECKED,
        content=content,
        provider="anthropic",
        model_snapshot="claude-haiku-4-5",
        prompt_version="summary-v1",
        input_hash="a" * 64,
    )


@pytest.mark.base
@pytest.mark.rag
def test_attach_updates_content_and_status_and_is_idempotent() -> None:
    summary = _summary_row(
        {
            "tldr": "Transformers explained.",
            "key_claims": ["Multi-head self-attention replaces recurrence."],
        }
    )

    changed = _attach_claim_provenance(summary, [ATTENTION_CHUNK, TRAINING_CHUNK])

    assert changed
    assert summary.source_match_status is SourceMatchStatus.MATCHED
    stored = StructuredSummary.model_validate(summary.content)
    assert stored.claims[0].matched
    assert stored.claims[0].source is not None
    assert stored.claims[0].source.chunk_id == ATTENTION_CHUNK.id

    assert not _attach_claim_provenance(summary, [ATTENTION_CHUNK, TRAINING_CHUNK])


@pytest.mark.base
@pytest.mark.rag
def test_attach_without_chunks_or_claims_changes_nothing() -> None:
    summary = _summary_row({"tldr": "No claims here."})
    assert not _attach_claim_provenance(summary, [ATTENTION_CHUNK])
    assert summary.source_match_status is SourceMatchStatus.NOT_CHECKED

    with_claims = _summary_row({"tldr": "Claims.", "key_claims": ["Anything."]})
    assert not _attach_claim_provenance(with_claims, [])
    assert with_claims.source_match_status is SourceMatchStatus.NOT_CHECKED


@pytest.mark.base
@pytest.mark.rag
def test_fully_unsupported_claims_mark_summary_unmatched() -> None:
    summary = _summary_row(
        {
            "tldr": "Unrelated summary.",
            "key_claims": ["Quantum annealing beats classical solvers."],
        }
    )

    assert _attach_claim_provenance(summary, [ATTENTION_CHUNK, TRAINING_CHUNK])
    assert summary.source_match_status is SourceMatchStatus.UNMATCHED
    stored = StructuredSummary.model_validate(summary.content)
    assert stored.claims[0].source is None


@pytest.mark.base
@pytest.mark.api
def test_summary_schema_serializes_claims_with_provenance() -> None:
    summary = _summary_row(
        {
            "tldr": "Transformers explained.",
            "key_claims": ["Multi-head self-attention replaces recurrence."],
        }
    )
    _attach_claim_provenance(summary, [ATTENTION_CHUNK])

    payload = Summary.from_stored(summary).model_dump(mode="json")

    assert payload["key_claims"] == ["Multi-head self-attention replaces recurrence."]
    claim = payload["claims"][0]
    assert claim["matched"] is True
    assert claim["source"]["chunk_id"] == str(ATTENTION_CHUNK.id)
    assert claim["source"]["section_title"] == "Model Architecture"
    assert claim["source"]["excerpt"] in ATTENTION_CHUNK.content


@pytest.mark.base
@pytest.mark.api
def test_summary_schema_accepts_rows_stored_before_provenance() -> None:
    legacy = _summary_row(
        {
            "tldr": "A grounded assistant that cites sources.",
            "key_claims": ["Grounded answers improve trust."],
            "methodology": "Retrieval plus citation checking.",
            "limitations": "Single-paper scope.",
        }
    )

    payload = Summary.from_stored(legacy).model_dump(mode="json")

    assert payload["claims"] == []
    assert payload["source_match_status"] == "not_checked"


class _StageSession:
    """Identity-map stand-in for driving the summarize stage with fakes."""

    def __init__(self, paper: object, version: object) -> None:
        self._paper = paper
        self._version = version

    async def get(self, model: type, identity: object, **kwargs: object) -> object | None:
        del kwargs
        from mneme.models.paper import Paper, PaperVersion

        if model is Paper and getattr(self._paper, "id", None) == identity:
            return self._paper
        if model is PaperVersion and getattr(self._version, "id", None) == identity:
            return self._version
        return None


@pytest.mark.base
@pytest.mark.rag
def test_summarize_stage_backfills_provenance_on_cache_hit_without_model_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reused summary gains provenance once chunks exist; no tokens spent."""
    import asyncio

    import mneme.ai.pipeline as pipeline_module
    from mneme.models.paper import Paper, PaperVersion, ProcessingStatus

    paper_id = uuid4()
    version_id = uuid4()
    paper = Paper(
        id=paper_id,
        arxiv_id=f"prov-test.{paper_id.hex[:8]}",
        title="Attention Is All You Need",
        abstract="Transformers explained.",
        primary_category="cs.LG",
        categories=["cs.LG"],
        pdf_url="https://arxiv.org/pdf/prov-test",
        processing_status=ProcessingStatus.READY,
    )
    version = PaperVersion(id=version_id, paper_id=paper_id, version_number=1)
    existing = _summary_row(
        {
            "tldr": "Transformers explained.",
            "key_claims": ["Multi-head self-attention replaces recurrence."],
        }
    )
    existing.paper_id = paper_id
    existing.paper_version_id = version_id

    class CachedArtifacts:
        def __init__(self, session: object) -> None:
            del session

        async def find_summary_by_input(self, **kwargs: object) -> PaperSummary:
            del kwargs
            return existing

        async def list_chunks_for_version(self, *, paper_version_id: UUID) -> list[Chunk]:
            assert paper_version_id == version_id
            return [ATTENTION_CHUNK, TRAINING_CHUNK]

    class ExplodingSummarizer:
        max_input_chars = 10_000

        async def summarize(self, **kwargs: object) -> None:
            raise AssertionError("cache hit must not regenerate")

    monkeypatch.setattr(pipeline_module, "ArtifactRepository", CachedArtifacts)
    stored = asyncio.run(
        pipeline_module.summarize_paper_stage(
            _StageSession(paper, version),  # type: ignore[arg-type]
            paper_id=paper_id,
            paper_version_id=version_id,
            summarizer=ExplodingSummarizer(),  # type: ignore[arg-type]
        )
    )

    assert stored is existing
    assert stored.source_match_status is SourceMatchStatus.MATCHED
    validated = StructuredSummary.model_validate(stored.content)
    assert validated.claims[0].source is not None
    assert validated.claims[0].source.chunk_id == ATTENTION_CHUNK.id


@pytest.mark.base
@pytest.mark.rag
def test_empty_replacement_clears_stale_provenance() -> None:
    """Replacing all chunks with none must not leave dead chunk references."""
    summary = _summary_row(
        {
            "tldr": "Transformers explained.",
            "key_claims": ["Multi-head self-attention replaces recurrence."],
        }
    )
    assert _attach_claim_provenance(summary, [ATTENTION_CHUNK])
    assert summary.source_match_status is SourceMatchStatus.MATCHED

    assert _attach_claim_provenance(summary, [], chunks_replaced=True)

    assert summary.source_match_status is SourceMatchStatus.UNMATCHED
    stored = StructuredSummary.model_validate(summary.content)
    assert stored.claims[0].matched is False
    assert stored.claims[0].source is None
    assert str(ATTENTION_CHUNK.id) not in str(summary.content)


@pytest.mark.base
@pytest.mark.rag
def test_chunk_stage_recomputes_provenance_on_empty_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The chunk stage itself must invalidate provenance when drafts are empty."""
    import asyncio

    import mneme.ai.pipeline as pipeline_module
    from mneme.models.paper import Paper, PaperVersion, ProcessingStatus

    paper_id = uuid4()
    version_id = uuid4()
    paper = Paper(
        id=paper_id,
        arxiv_id=f"prov-stage.{paper_id.hex[:8]}",
        title="Attention Is All You Need",
        abstract="Transformers explained.",
        primary_category="cs.LG",
        categories=["cs.LG"],
        pdf_url="https://arxiv.org/pdf/prov-stage",
        processing_status=ProcessingStatus.READY,
    )
    version = PaperVersion(id=version_id, paper_id=paper_id, version_number=1)
    summary = _summary_row(
        {
            "tldr": "Transformers explained.",
            "key_claims": ["Multi-head self-attention replaces recurrence."],
        }
    )
    summary.paper_id = paper_id
    summary.paper_version_id = version_id
    assert _attach_claim_provenance(summary, [ATTENTION_CHUNK])

    class ReplacingArtifacts:
        def __init__(self, session: object) -> None:
            del session

        async def replace_chunks(self, *, paper_id: UUID, paper_version_id: UUID, drafts: list):
            del paper_id, paper_version_id
            return drafts

        async def list_summaries_for_version(self, *, paper_version_id: UUID) -> list:
            assert paper_version_id == version_id
            return [summary]

    monkeypatch.setattr(pipeline_module, "ArtifactRepository", ReplacingArtifacts)
    count = asyncio.run(
        pipeline_module.chunk_paper_stage(
            _StageSession(paper, version),  # type: ignore[arg-type]
            paper_id=paper_id,
            paper_version_id=version_id,
            sections=[],
            max_tokens=100,
            overlap_tokens=10,
        )
    )

    assert count == 0
    assert summary.source_match_status is SourceMatchStatus.UNMATCHED
    stored = StructuredSummary.model_validate(summary.content)
    assert stored.claims[0].source is None
