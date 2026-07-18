"""Structured summarization: prompt, parsing, fallback, and idempotent hash."""

import asyncio
import json
from decimal import Decimal
from typing import cast

import pytest
from conftest import FakeRedis
from redis.asyncio import Redis

from mneme.ai.budget import BudgetGuard
from mneme.ai.cache import LLMCache
from mneme.ai.prompts import SUMMARY_PROMPT_VERSION, build_summary_request
from mneme.ai.providers import LLMProvider
from mneme.ai.providers.fake import FakeLLMProvider
from mneme.ai.routing import ModelRouter
from mneme.ai.service import LLMService
from mneme.ai.summarization import (
    SummarizationService,
    SummaryParseError,
    parse_summary_response,
    summary_input_hash,
)
from mneme.ai.types import AITask, ProviderName
from mneme.models.artifact import SummaryStatus

VALID_PAYLOAD = {
    "tldr": "The paper proposes a new attention-only architecture.",
    "key_claims": ["Attention replaces recurrence.", "Training is faster."],
    "methodology": "Encoder-decoder built from multi-head self-attention.",
    "limitations": "Only evaluated on translation.",
}


def _service(provider: FakeLLMProvider) -> SummarizationService:
    redis = cast(Redis, FakeRedis())
    llm = LLMService(
        router=ModelRouter({AITask.SUMMARIZE: "claude-haiku-4-5", AITask.QA: "claude-haiku-4-5"}),
        providers={ProviderName.ANTHROPIC: cast(LLMProvider, provider)},
        cache=LLMCache(
            redis, enabled=True, ttl_seconds={AITask.SUMMARIZE: 604800, AITask.QA: 86400}
        ),
        budget=BudgetGuard(redis, daily_cap_usd=Decimal("5")),
    )
    return SummarizationService(llm, max_input_chars=10_000, max_output_tokens=512)


@pytest.mark.base
def test_valid_json_response_parses_into_structured_summary() -> None:
    summary = parse_summary_response(json.dumps(VALID_PAYLOAD))

    assert summary.tldr == VALID_PAYLOAD["tldr"]
    assert list(summary.key_claims) == VALID_PAYLOAD["key_claims"]
    assert summary.methodology == VALID_PAYLOAD["methodology"]
    assert summary.limitations == VALID_PAYLOAD["limitations"]


@pytest.mark.base
def test_markdown_fenced_json_still_parses() -> None:
    fenced = f"```json\n{json.dumps(VALID_PAYLOAD)}\n```"

    summary = parse_summary_response(fenced)

    assert summary.tldr == VALID_PAYLOAD["tldr"]


@pytest.mark.base
def test_prose_response_raises_parse_error() -> None:
    with pytest.raises(SummaryParseError):
        parse_summary_response("This paper is about transformers and attention.")


@pytest.mark.base
def test_invalid_schema_raises_parse_error() -> None:
    with pytest.raises(SummaryParseError):
        parse_summary_response(json.dumps({"summary": "wrong keys"}))


@pytest.mark.base
@pytest.mark.rag
def test_summarize_returns_ready_structured_summary_for_parsed_body() -> None:
    provider = FakeLLMProvider(default_response=json.dumps(VALID_PAYLOAD))
    service = _service(provider)

    generation = asyncio.run(
        service.summarize(
            title="Attention Is All You Need",
            abstract="An abstract about attention.",
            body="Full parsed text of the paper.",
        )
    )

    assert generation.status is SummaryStatus.READY
    assert generation.summary.tldr == VALID_PAYLOAD["tldr"]
    assert generation.completion.prompt_version == SUMMARY_PROMPT_VERSION
    assert len(generation.input_hash) == 64


@pytest.mark.base
@pytest.mark.rag
def test_abstract_only_summary_is_partial() -> None:
    provider = FakeLLMProvider(default_response=json.dumps(VALID_PAYLOAD))
    service = _service(provider)

    generation = asyncio.run(
        service.summarize(title="T", abstract="An abstract about attention.", body=None)
    )

    assert generation.status is SummaryStatus.PARTIAL


@pytest.mark.base
@pytest.mark.rag
def test_unparseable_response_degrades_to_partial_fallback() -> None:
    provider = FakeLLMProvider(
        default_response="The paper introduces attention. It removes recurrence entirely."
    )
    service = _service(provider)

    generation = asyncio.run(
        service.summarize(title="T", abstract="Fallback abstract.", body="Parsed body text.")
    )

    assert generation.status is SummaryStatus.PARTIAL
    assert "attention" in generation.summary.tldr
    assert generation.summary.key_claims == ()


@pytest.mark.base
def test_input_hash_changes_with_body_and_prompt_inputs() -> None:
    base = summary_input_hash(title="T", body="body-1")

    assert base == summary_input_hash(title="T", body="body-1")
    assert base != summary_input_hash(title="T", body="body-2")
    assert base != summary_input_hash(title="Other", body="body-1")


@pytest.mark.base
def test_summary_request_routes_to_summarize_task_with_version() -> None:
    request = build_summary_request(title="T", body="B", max_output_tokens=256)

    assert request.task is AITask.SUMMARIZE
    assert request.prompt_version == SUMMARY_PROMPT_VERSION
    assert request.system is not None and "JSON" in request.system
    assert "Title: T" in request.messages[0].content
