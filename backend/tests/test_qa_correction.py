"""Bounded Q&A citation correction: pass-through, one retry, explicit unresolved."""

import asyncio
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest
from conftest import FakeRedis
from redis.asyncio import Redis

from mneme.ai.budget import BudgetGuard
from mneme.ai.cache import LLMCache
from mneme.ai.prompts import (
    QA_CORRECTION_PROMPT_VERSION,
    QA_PROMPT_VERSION,
    build_qa_correction_request,
    build_qa_request,
)
from mneme.ai.providers import LLMProvider
from mneme.ai.providers.fake import FakeLLMProvider
from mneme.ai.qa import (
    REFUSAL_ANSWER,
    UNRESOLVED_ANSWER,
    GroundedAnswerService,
    _render_evidence,
)
from mneme.ai.retrieval import RetrievedChunk
from mneme.ai.routing import ModelRouter
from mneme.ai.service import LLMService
from mneme.ai.types import AITask, ProviderName
from mneme.models.qa import QaCitationResolution, QaSourceMatchStatus

PAPER_ID = uuid4()
QUESTION = "How does the attention mechanism replace recurrence?"

SUPPORTED_ANSWER = "Multi-head attention replaces recurrence with parallel heads [1]."
UNSUPPORTED_ANSWER = "The model was trained on seventeen proprietary datasets [1]."
INVALID_MARKER_ANSWER = "Attention replaces recurrence entirely [7]."


def _chunk(index: int, content: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        paper_id=PAPER_ID,
        chunk_index=index,
        section_title=f"Section {index}",
        content=content,
        score=score,
    )


def _evidence() -> list[RetrievedChunk]:
    return [
        _chunk(0, "Multi-head attention replaces recurrence with parallel attention heads.", 0.9),
        _chunk(1, "Positional encodings inject order information into the model.", 0.8),
    ]


def _service(provider: FakeLLMProvider) -> GroundedAnswerService:
    redis = cast(Redis, FakeRedis())
    llm = LLMService(
        router=ModelRouter({AITask.SUMMARIZE: "claude-haiku-4-5", AITask.QA: "claude-haiku-4-5"}),
        providers={ProviderName.ANTHROPIC: cast(LLMProvider, provider)},
        cache=LLMCache(
            redis, enabled=True, ttl_seconds={AITask.SUMMARIZE: 604800, AITask.QA: 86400}
        ),
        budget=BudgetGuard(redis, daily_cap_usd=Decimal("5")),
    )
    return GroundedAnswerService(llm, rerank_top_n=3, min_evidence_score=0.2, max_output_tokens=256)


def _prompts(first_answer: str) -> tuple[str, str]:
    """The exact first-pass and correction user messages for the fixed evidence."""
    evidence = [_render_evidence(chunk) for chunk in _evidence()]
    first = (
        build_qa_request(question=QUESTION, evidence=evidence, max_output_tokens=256)
        .messages[0]
        .content
    )
    correction = (
        build_qa_correction_request(
            question=QUESTION,
            evidence=evidence,
            previous_answer=first_answer,
            max_output_tokens=256,
        )
        .messages[0]
        .content
    )
    return first, correction


def _answer(provider: FakeLLMProvider):
    return asyncio.run(_service(provider).answer(question=QUESTION, chunks=_evidence()))


@pytest.mark.base
@pytest.mark.rag
def test_valid_first_answer_returns_without_second_model_call() -> None:
    first_prompt, _ = _prompts("unused")
    provider = FakeLLMProvider(responses={first_prompt: SUPPORTED_ANSWER})

    grounded = _answer(provider)

    assert grounded.answer == SUPPORTED_ANSWER
    assert grounded.citation_resolution is QaCitationResolution.VERIFIED
    assert grounded.source_match_status is QaSourceMatchStatus.MATCHED
    assert grounded.model_calls == 1
    assert len(provider.calls) == 1


@pytest.mark.base
@pytest.mark.rag
def test_invalid_marker_triggers_exactly_one_correction() -> None:
    first_prompt, correction_prompt = _prompts(INVALID_MARKER_ANSWER)
    provider = FakeLLMProvider(
        responses={
            first_prompt: INVALID_MARKER_ANSWER,
            correction_prompt: SUPPORTED_ANSWER,
        }
    )

    grounded = _answer(provider)

    assert grounded.answer == SUPPORTED_ANSWER
    assert grounded.citation_resolution is QaCitationResolution.CORRECTED
    assert grounded.source_match_status is QaSourceMatchStatus.MATCHED
    assert grounded.model_calls == 2
    assert len(provider.calls) == 2
    assert provider.calls[1][1].prompt_version == QA_CORRECTION_PROMPT_VERSION


@pytest.mark.base
@pytest.mark.rag
def test_unsupported_citation_triggers_correction() -> None:
    first_prompt, correction_prompt = _prompts(UNSUPPORTED_ANSWER)
    provider = FakeLLMProvider(
        responses={
            first_prompt: UNSUPPORTED_ANSWER,
            correction_prompt: SUPPORTED_ANSWER,
        }
    )

    grounded = _answer(provider)

    assert grounded.answer == SUPPORTED_ANSWER
    assert grounded.citation_resolution is QaCitationResolution.CORRECTED
    assert grounded.model_calls == 2


@pytest.mark.base
@pytest.mark.rag
def test_failed_correction_returns_explicit_unresolved_state() -> None:
    first_prompt, correction_prompt = _prompts(UNSUPPORTED_ANSWER)
    provider = FakeLLMProvider(
        responses={
            first_prompt: UNSUPPORTED_ANSWER,
            correction_prompt: INVALID_MARKER_ANSWER,
        }
    )

    grounded = _answer(provider)

    assert grounded.answer == UNRESOLVED_ANSWER
    assert grounded.citations == ()
    assert grounded.citation_resolution is QaCitationResolution.UNRESOLVED
    assert grounded.source_match_status is QaSourceMatchStatus.INSUFFICIENT_EVIDENCE
    assert grounded.model_calls == 2
    assert len(provider.calls) == 2, "the correction pass is bounded to one attempt"


@pytest.mark.base
@pytest.mark.rag
def test_correction_refusal_is_an_honest_insufficient_state() -> None:
    first_prompt, correction_prompt = _prompts(UNSUPPORTED_ANSWER)
    provider = FakeLLMProvider(
        responses={
            first_prompt: UNSUPPORTED_ANSWER,
            correction_prompt: "INSUFFICIENT_EVIDENCE",
        }
    )

    grounded = _answer(provider)

    assert grounded.answer == REFUSAL_ANSWER
    assert grounded.citation_resolution is QaCitationResolution.CORRECTED
    assert grounded.source_match_status is QaSourceMatchStatus.INSUFFICIENT_EVIDENCE
    assert grounded.model_calls == 2


@pytest.mark.base
@pytest.mark.rag
def test_first_pass_refusal_never_triggers_correction() -> None:
    first_prompt, _ = _prompts("unused")
    provider = FakeLLMProvider(responses={first_prompt: "INSUFFICIENT_EVIDENCE"})

    grounded = _answer(provider)

    assert grounded.answer == REFUSAL_ANSWER
    assert grounded.citation_resolution is QaCitationResolution.NOT_APPLICABLE
    assert grounded.model_calls == 1
    assert len(provider.calls) == 1


@pytest.mark.base
@pytest.mark.rag
def test_weak_evidence_refusal_spends_no_model_calls() -> None:
    provider = FakeLLMProvider()
    service = _service(provider)

    grounded = asyncio.run(
        service.answer(
            question=QUESTION,
            chunks=[_chunk(0, "unrelated words entirely", 0.05)],
        )
    )

    assert grounded.answer == REFUSAL_ANSWER
    assert grounded.citation_resolution is QaCitationResolution.NOT_APPLICABLE
    assert grounded.model_calls == 0
    assert provider.calls == []


@pytest.mark.base
@pytest.mark.rag
def test_correction_cost_accounting_covers_both_calls() -> None:
    first_prompt, correction_prompt = _prompts(UNSUPPORTED_ANSWER)
    provider = FakeLLMProvider(
        responses={
            first_prompt: UNSUPPORTED_ANSWER,
            correction_prompt: SUPPORTED_ANSWER,
        }
    )

    grounded = _answer(provider)

    assert len(grounded.completions) == 2
    total = sum(item.estimated_cost for item in grounded.completions)
    assert total > grounded.completions[-1].estimated_cost >= Decimal(0)
    assert grounded.completion is grounded.completions[-1]


@pytest.mark.base
@pytest.mark.rag
def test_corrected_answers_are_served_from_cache_on_identical_reask() -> None:
    first_prompt, correction_prompt = _prompts(UNSUPPORTED_ANSWER)
    provider = FakeLLMProvider(
        responses={
            first_prompt: UNSUPPORTED_ANSWER,
            correction_prompt: SUPPORTED_ANSWER,
        }
    )
    service = _service(provider)

    first_run = asyncio.run(service.answer(question=QUESTION, chunks=_evidence()))
    second_run = asyncio.run(service.answer(question=QUESTION, chunks=_evidence()))

    assert first_run.answer == second_run.answer == SUPPORTED_ANSWER
    assert second_run.citation_resolution is QaCitationResolution.CORRECTED
    assert len(provider.calls) == 2, "the identical re-ask is served from cache"
    assert all(item.cached for item in second_run.completions)


@pytest.mark.base
@pytest.mark.rag
def test_correction_request_is_deterministic_and_versioned() -> None:
    evidence = [_render_evidence(chunk) for chunk in _evidence()]
    request = build_qa_correction_request(
        question=QUESTION,
        evidence=evidence,
        previous_answer=UNSUPPORTED_ANSWER,
        max_output_tokens=256,
    )

    assert request.prompt_version == QA_CORRECTION_PROMPT_VERSION
    assert request.prompt_version != QA_PROMPT_VERSION
    assert request.task is AITask.QA
    first = build_qa_request(question=QUESTION, evidence=evidence, max_output_tokens=256)
    assert request.system == first.system
    assert UNSUPPORTED_ANSWER in request.messages[0].content
    assert request.messages[0].content.startswith("Evidence excerpts:")
    again = build_qa_correction_request(
        question=QUESTION,
        evidence=evidence,
        previous_answer=UNSUPPORTED_ANSWER,
        max_output_tokens=256,
    )
    assert request == again
