"""Evaluation fixtures and harness aggregation."""

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from mneme.ai.evaluation import (
    EvaluationHarness,
    QAFixture,
    RagCaseOutcome,
    RagEvaluationHarness,
    RagRunConfig,
    load_qa_fixtures,
)
from mneme.ai.evaluation.harness import keyword_coverage, section_hint_hit
from mneme.ai.providers import FakeLLMProvider
from mneme.ai.types import (
    AITask,
    ChatMessage,
    CompletionRequest,
    CompletionResult,
    ProviderName,
    TokenUsage,
)
from mneme.models.qa import QaSourceMatchStatus

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "eval" / "qa_seed_v1.json"
FIXTURE_V2_PATH = Path(__file__).parent / "fixtures" / "eval" / "qa_seed_v2.json"


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


@pytest.mark.base
@pytest.mark.rag
def test_seed_v2_expands_to_fifteen_fixtures_with_refusals() -> None:
    fixture_file = load_qa_fixtures(FIXTURE_V2_PATH)

    assert fixture_file.fixture_version == "qa-seed-v2"
    assert len(fixture_file.fixtures) == 15
    refusals = [fixture for fixture in fixture_file.fixtures if fixture.expect_refusal]
    answerable = [fixture for fixture in fixture_file.fixtures if not fixture.expect_refusal]
    assert len(refusals) == 3
    assert all(not fixture.must_cite for fixture in refusals)
    assert all(fixture.must_cite for fixture in answerable)
    assert all(fixture.expected_keywords for fixture in answerable)
    assert all(fixture.section_hint for fixture in answerable)


@pytest.mark.base
@pytest.mark.rag
def test_seed_v2_pins_an_exact_arxiv_revision_per_fixture() -> None:
    fixture_file = load_qa_fixtures(FIXTURE_V2_PATH)

    assert all(fixture.arxiv_version is not None for fixture in fixture_file.fixtures)
    # Every fixture against the same paper pins the same revision.
    pins: dict[str, int] = {}
    for fixture in fixture_file.fixtures:
        assert fixture.arxiv_version is not None
        assert pins.setdefault(fixture.arxiv_id, fixture.arxiv_version) == fixture.arxiv_version
    assert len(pins) == 7


@pytest.mark.base
@pytest.mark.rag
def test_seed_v2_keeps_v1_fixture_ids_for_metric_continuity() -> None:
    v1_ids = {fixture.fixture_id for fixture in load_qa_fixtures(FIXTURE_PATH).fixtures}
    v2_ids = {fixture.fixture_id for fixture in load_qa_fixtures(FIXTURE_V2_PATH).fixtures}

    assert v1_ids <= v2_ids


@pytest.mark.base
@pytest.mark.rag
def test_refusal_fixture_rejects_must_cite() -> None:
    with pytest.raises(ValidationError, match="must_cite"):
        QAFixture(
            fixture_id="qa-x",
            arxiv_id="0000.00000",
            question="Out of scope?",
            reference_answer="Refuse.",
            must_cite=True,
            expect_refusal=True,
        )


@pytest.mark.base
@pytest.mark.rag
def test_answerable_fixture_requires_keywords() -> None:
    with pytest.raises(ValidationError, match="keyword"):
        QAFixture(
            fixture_id="qa-x",
            arxiv_id="0000.00000",
            question="Answerable?",
            reference_answer="Yes.",
        )


def _refusal_fixture(fixture_id: str = "qa-refusal") -> QAFixture:
    return QAFixture(
        fixture_id=fixture_id,
        arxiv_id="0000.00000",
        question="Out of scope?",
        reference_answer="Refuse.",
        must_cite=False,
        expect_refusal=True,
    )


@pytest.mark.base
@pytest.mark.rag
def test_keyword_coverage_rejects_empty_keyword_set() -> None:
    with pytest.raises(ValueError, match="at least one expected keyword"):
        keyword_coverage("any answer", ())


@pytest.mark.base
@pytest.mark.rag
def test_legacy_harness_rejects_refusal_fixtures() -> None:
    """Regression: refusal fixtures used to crash keyword grading with ZeroDivisionError."""

    async def answer(fixture: QAFixture) -> CompletionResult:
        raise AssertionError("must reject before calling the answer function")

    with pytest.raises(ValueError, match="qa-refusal"):
        asyncio.run(
            EvaluationHarness(answer).run((_refusal_fixture(),), fixture_version="qa-seed-v2")
        )


@pytest.mark.base
@pytest.mark.rag
def test_section_hint_matches_numbered_and_partial_titles() -> None:
    assert section_hint_hit("Model Architecture", ("3 Model Architecture",))
    assert section_hint_hit("3.2 Attention", ("Attention",))
    assert not section_hint_hit("Method", ("Introduction", "Related Work"))
    assert not section_hint_hit("Method", ())


def _completion(text: str) -> CompletionResult:
    return CompletionResult(
        text=text,
        task=AITask.QA,
        provider=ProviderName.ANTHROPIC,
        model="claude-haiku-4-5",
        prompt_version="qa-v2",
        usage=TokenUsage(input_tokens=100, output_tokens=50),
        estimated_cost=Decimal("0.002"),
        latency_ms=20,
    )


@pytest.mark.base
@pytest.mark.rag
def test_rag_harness_grades_retrieval_grounding_and_refusals() -> None:
    fixture_file = load_qa_fixtures(FIXTURE_V2_PATH)
    refused_ids = {"qa-013-transformer-dollar-budget", "qa-014-lora-diffusion-scope"}
    false_refusal_id = "qa-012-vit-patches"
    partial_id = "qa-010-dpo-loss-form"
    uncited_id = "qa-011-bert-pretraining"

    async def answer(fixture: QAFixture) -> RagCaseOutcome:
        if fixture.fixture_id in refused_ids or fixture.fixture_id == false_refusal_id:
            return RagCaseOutcome(
                answer="The paper does not contain enough evidence to answer this question.",
                refused=True,
            )
        if fixture.fixture_id == partial_id:
            status = QaSourceMatchStatus.PARTIAL
        elif fixture.fixture_id == uncited_id:
            status = QaSourceMatchStatus.INSUFFICIENT_EVIDENCE
        else:
            status = QaSourceMatchStatus.MATCHED
        text = " ".join(fixture.expected_keywords) + " [1]"
        return RagCaseOutcome(
            answer=text,
            refused=False,
            dense_sections=(fixture.section_hint,) if fixture.section_hint else (),
            source_match_status=status,
            verified_citations=0 if fixture.fixture_id == uncited_id else 2,
            completion=_completion(text),
        )

    report = asyncio.run(
        RagEvaluationHarness(answer).run(
            fixture_file.fixtures, fixture_version=fixture_file.fixture_version
        )
    )

    assert len(report.cases) == 15
    # 12 answerable fixtures carry section hints; only the false refusal misses.
    assert report.recall_at_k == pytest.approx(11 / 12)
    # 11 answered: 9 matched, 1 partial, 1 insufficient.
    assert report.source_match_rate == pytest.approx(9 / 11)
    assert report.partial_match_rate == pytest.approx(1 / 11)
    assert report.citation_rate == pytest.approx(10 / 11)
    # 2 of 3 expected refusals refused; qa-015 was wrongly answered.
    assert report.refusal_accuracy == pytest.approx(2 / 3)
    assert report.false_refusal_rate == pytest.approx(1 / 12)
    assert report.mean_keyword_coverage == pytest.approx(1.0)
    # 11 answered + 1 wrongly answered refusal case hit the provider.
    assert report.total_generation_cost == Decimal("0.024")
    assert report.mean_generation_latency_ms == pytest.approx(20.0)

    by_id = {case.fixture_id: case for case in report.cases}
    assert by_id[false_refusal_id].refusal_correct is False
    assert by_id[false_refusal_id].keyword_coverage is None
    assert by_id["qa-015-rag-clinical-scope"].refusal_correct is False
    assert by_id["qa-013-transformer-dollar-budget"].refusal_correct is True
    assert by_id["qa-013-transformer-dollar-budget"].generation_cost == Decimal(0)
    assert by_id["qa-013-transformer-dollar-budget"].generation_latency_ms == 0


@pytest.mark.base
@pytest.mark.rag
def test_rag_harness_grades_recall_on_dense_results_only() -> None:
    """A section reached only via a context anchor must not count as a hit."""
    fixture = QAFixture(
        fixture_id="qa-anchor",
        arxiv_id="0000.00000",
        arxiv_version=1,
        section_hint="Model Architecture",
        question="Q?",
        reference_answer="A.",
        expected_keywords=("anything",),
    )

    async def answer(_: QAFixture) -> RagCaseOutcome:
        return RagCaseOutcome(
            answer="anything [1]",
            refused=False,
            dense_sections=("Related Work",),
            anchor_sections=("1 Model Architecture",),
            source_match_status=QaSourceMatchStatus.MATCHED,
            verified_citations=1,
            completion=_completion("anything [1]"),
        )

    report = asyncio.run(RagEvaluationHarness(answer).run((fixture,), fixture_version="qa-seed-v2"))

    assert report.recall_at_k == 0.0


@pytest.mark.base
@pytest.mark.rag
def test_rag_harness_separates_cached_metadata_from_incremental_spend() -> None:
    """Cached generations keep their metadata but contribute no run spend."""
    fixture_file = load_qa_fixtures(FIXTURE_PATH)
    fixtures = fixture_file.fixtures[:2]
    cached_id = fixtures[0].fixture_id
    embed_cost = Decimal("0.0001")

    async def answer(fixture: QAFixture) -> RagCaseOutcome:
        text = " ".join(fixture.expected_keywords) + " [1]"
        completion = _completion(text).model_copy(
            update={"cached": fixture.fixture_id == cached_id}
        )
        return RagCaseOutcome(
            answer=text,
            refused=False,
            dense_sections=(fixture.section_hint,) if fixture.section_hint else (),
            source_match_status=QaSourceMatchStatus.MATCHED,
            verified_citations=1,
            completion=completion,
            query_embedding_cost=embed_cost,
            pipeline_latency_ms=120,
        )

    report = asyncio.run(RagEvaluationHarness(answer).run(fixtures, fixture_version="qa-seed-v1"))

    by_id = {case.fixture_id: case for case in report.cases}
    cached_case = by_id[cached_id]
    uncached_case = next(case for case in report.cases if case.fixture_id != cached_id)
    # The cached hit still reports the original generation's metadata...
    assert cached_case.generation_cost == Decimal("0.002")
    assert cached_case.generation_latency_ms == 20
    # ...but this run only spent the query embedding on it.
    assert cached_case.incremental_cost == embed_cost
    assert uncached_case.incremental_cost == embed_cost + Decimal("0.002")
    assert report.total_generation_cost == Decimal("0.004")
    assert report.total_incremental_cost == embed_cost * 2 + Decimal("0.002")
    assert report.mean_generation_latency_ms == pytest.approx(20.0)
    assert report.mean_pipeline_latency_ms == pytest.approx(120.0)


@pytest.mark.base
@pytest.mark.rag
def test_rag_harness_embeds_run_config_provenance() -> None:
    fixture_file = load_qa_fixtures(FIXTURE_PATH)
    run_config = RagRunConfig(
        llm_provider="anthropic",
        llm_model="claude-haiku-4-5",
        prompt_version="qa-v2",
        embedding_backend="openai",
        embedding_model="text-embedding-3-small",
        retrieval_top_k=8,
        context_anchor_count=2,
        rerank_top_n=4,
        min_evidence_score=0.25,
        max_output_tokens=512,
        cache_enabled=True,
        qa_cache_ttl_seconds=86400,
    )

    async def answer(fixture: QAFixture) -> RagCaseOutcome:
        return RagCaseOutcome(answer="x", refused=True)

    report = asyncio.run(
        RagEvaluationHarness(answer).run(
            fixture_file.fixtures[:1],
            fixture_version=fixture_file.fixture_version,
            run_config=run_config,
        )
    )

    assert report.run_config == run_config
