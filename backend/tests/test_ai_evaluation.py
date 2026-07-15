"""Evaluation fixtures and harness aggregation."""

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from mneme.ai.evaluation import EvaluationHarness, QAFixture, load_qa_fixtures
from mneme.ai.providers import FakeLLMProvider
from mneme.ai.types import (
    AITask,
    ChatMessage,
    CompletionRequest,
    CompletionResult,
    ProviderName,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "eval" / "qa_seed_v1.json"


@pytest.mark.base
@pytest.mark.rag
def test_seed_file_defines_five_unique_fixtures() -> None:
    fixture_file = load_qa_fixtures(FIXTURE_PATH)

    assert fixture_file.fixture_version == "qa-seed-v1"
    assert len(fixture_file.fixtures) == 5
    assert all(fixture.must_cite for fixture in fixture_file.fixtures)
    assert all(fixture.expected_keywords for fixture in fixture_file.fixtures)


@pytest.mark.base
@pytest.mark.rag
def test_harness_aggregates_quality_and_cost_telemetry() -> None:
    fixture_file = load_qa_fixtures(FIXTURE_PATH)
    first = fixture_file.fixtures[0]
    provider = FakeLLMProvider(
        responses={
            # Full keyword coverage for the first fixture only.
            first.question: "It uses multi-head self-attention; attention replaces recurrence.",
        },
        default_response="The paper does not say.",
    )

    async def answer(fixture: QAFixture) -> CompletionResult:
        response = await provider.complete(
            model="claude-haiku-4-5",
            request=CompletionRequest(
                task=AITask.QA,
                messages=(ChatMessage(role="user", content=fixture.question),),
                prompt_version="v1",
            ),
        )
        return CompletionResult(
            text=response.text,
            task=AITask.QA,
            provider=ProviderName.ANTHROPIC,
            model=response.model,
            prompt_version="v1",
            usage=response.usage,
            estimated_cost=Decimal("0.001"),
            latency_ms=10,
        )

    report = asyncio.run(
        EvaluationHarness(answer).run(
            fixture_file.fixtures, fixture_version=fixture_file.fixture_version
        )
    )

    assert len(report.cases) == 5
    assert report.cases[0].keyword_coverage == 1.0
    assert all(case.keyword_coverage == 0.0 for case in report.cases[1:])
    assert report.mean_keyword_coverage == pytest.approx(0.2)
    assert report.total_estimated_cost == Decimal("0.005")
    assert report.total_output_tokens > 0
    assert len(provider.calls) == 5
