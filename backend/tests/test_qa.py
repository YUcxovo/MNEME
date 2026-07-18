"""Grounded Q&A: rerank blending, citation verification, refusal paths."""

import asyncio
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest
from conftest import FakeRedis
from redis.asyncio import Redis

from mneme.ai.budget import BudgetGuard
from mneme.ai.cache import LLMCache
from mneme.ai.providers import LLMProvider
from mneme.ai.providers.fake import FakeLLMProvider
from mneme.ai.qa import (
    REFUSAL_ANSWER,
    GroundedAnswerService,
    lexical_overlap,
    rerank,
    verify_citations,
)
from mneme.ai.retrieval import RetrievedChunk
from mneme.ai.routing import ModelRouter
from mneme.ai.service import LLMService
from mneme.ai.types import AITask, ProviderName
from mneme.models.qa import QaSourceMatchStatus

PAPER_ID = uuid4()


def _chunk(index: int, content: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        paper_id=PAPER_ID,
        chunk_index=index,
        section_title=f"Section {index}",
        content=content,
        score=score,
    )


def _service(
    provider: FakeLLMProvider, *, min_evidence_score: float = 0.2
) -> GroundedAnswerService:
    redis = cast(Redis, FakeRedis())
    llm = LLMService(
        router=ModelRouter({AITask.SUMMARIZE: "claude-haiku-4-5", AITask.QA: "claude-haiku-4-5"}),
        providers={ProviderName.ANTHROPIC: cast(LLMProvider, provider)},
        cache=LLMCache(
            redis, enabled=True, ttl_seconds={AITask.SUMMARIZE: 604800, AITask.QA: 86400}
        ),
        budget=BudgetGuard(redis, daily_cap_usd=Decimal("5")),
    )
    return GroundedAnswerService(
        llm, rerank_top_n=3, min_evidence_score=min_evidence_score, max_output_tokens=256
    )


@pytest.mark.base
@pytest.mark.rag
def test_lexical_overlap_ignores_stopwords() -> None:
    assert lexical_overlap("what is the attention mechanism", "attention mechanism") == 1.0
    assert lexical_overlap("what is the attention mechanism", "convolution only") == 0.0


@pytest.mark.base
@pytest.mark.rag
def test_rerank_promotes_lexically_matching_chunks() -> None:
    vector_favorite = _chunk(0, "completely unrelated content words", 0.8)
    lexical_favorite = _chunk(1, "the attention mechanism uses query and key vectors", 0.7)

    ranked = rerank(
        "how does the attention mechanism work?",
        [vector_favorite, lexical_favorite],
        top_n=2,
    )

    assert ranked[0].chunk_index == 1
    assert ranked[0].score > ranked[1].score


@pytest.mark.base
@pytest.mark.rag
def test_rerank_is_deterministic_on_ties() -> None:
    chunks = [_chunk(0, "same words here", 0.5), _chunk(1, "same words here", 0.5)]

    first = rerank("unrelated question", chunks, top_n=2)
    second = rerank("unrelated question", chunks, top_n=2)

    assert [chunk.chunk_index for chunk in first] == [0, 1]
    assert first == second


@pytest.mark.base
@pytest.mark.rag
def test_verified_citations_mark_grounded_answer_as_matched() -> None:
    evidence = [
        _chunk(0, "The transformer uses multi-head attention for global dependencies", 0.9),
        _chunk(1, "Training used eight GPUs for twelve hours", 0.6),
    ]
    answer = "The model relies on multi-head attention [1]."

    citations, status = verify_citations(answer, evidence)

    assert status is QaSourceMatchStatus.MATCHED
    assert len(citations) == 1
    assert citations[0].marker == 1
    assert citations[0].source_match is True


@pytest.mark.base
@pytest.mark.rag
def test_out_of_range_markers_are_dropped_not_fabricated() -> None:
    evidence = [_chunk(0, "attention is the mechanism", 0.9)]
    answer = "Attention drives the model [1], as shown in ablations [7]."

    citations, _ = verify_citations(answer, evidence)

    assert [citation.marker for citation in citations] == [1]


@pytest.mark.base
@pytest.mark.rag
def test_uncited_answer_reports_insufficient_evidence() -> None:
    evidence = [_chunk(0, "attention content", 0.9)]

    citations, status = verify_citations("The paper is about attention.", evidence)

    assert citations == ()
    assert status is QaSourceMatchStatus.INSUFFICIENT_EVIDENCE


@pytest.mark.base
@pytest.mark.rag
def test_answer_flow_returns_verified_citations() -> None:
    provider = FakeLLMProvider(
        default_response="The transformer replaces recurrence with multi-head attention [1]."
    )
    service = _service(provider)
    chunks = [
        _chunk(0, "The transformer uses multi-head attention instead of recurrence", 0.9),
        _chunk(1, "Datasets include WMT 2014 English-German", 0.5),
    ]

    grounded = asyncio.run(service.answer(question="what replaces recurrence?", chunks=chunks))

    assert grounded.source_match_status is QaSourceMatchStatus.MATCHED
    assert len(grounded.citations) == 1
    assert grounded.completion is not None


@pytest.mark.base
@pytest.mark.rag
def test_no_chunks_refuses_without_llm_call() -> None:
    provider = FakeLLMProvider()
    service = _service(provider)

    grounded = asyncio.run(service.answer(question="anything?", chunks=[]))

    assert grounded.answer == REFUSAL_ANSWER
    assert grounded.source_match_status is QaSourceMatchStatus.INSUFFICIENT_EVIDENCE
    assert provider.calls == []


@pytest.mark.base
@pytest.mark.rag
def test_weak_evidence_refuses_without_llm_call() -> None:
    provider = FakeLLMProvider()
    service = _service(provider, min_evidence_score=0.9)

    grounded = asyncio.run(
        service.answer(question="anything?", chunks=[_chunk(0, "unrelated", 0.3)])
    )

    assert grounded.answer == REFUSAL_ANSWER
    assert provider.calls == []


@pytest.mark.base
@pytest.mark.rag
def test_model_declared_insufficiency_becomes_stable_refusal() -> None:
    provider = FakeLLMProvider(default_response="INSUFFICIENT_EVIDENCE")
    service = _service(provider)

    grounded = asyncio.run(
        service.answer(
            question="what about pretraining data?",
            chunks=[_chunk(0, "the architecture uses attention layers", 0.9)],
        )
    )

    assert grounded.answer == REFUSAL_ANSWER
    assert grounded.citations == ()
    assert grounded.source_match_status is QaSourceMatchStatus.INSUFFICIENT_EVIDENCE
