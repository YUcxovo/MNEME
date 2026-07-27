"""Run fixtures through an answer function and aggregate quality/cost metrics."""

from collections.abc import Awaitable, Callable
from decimal import Decimal

import structlog
from pydantic import BaseModel, ConfigDict, Field

from mneme.ai.evaluation.fixtures import QAFixture
from mneme.ai.types import CompletionResult
from mneme.models.qa import QaSourceMatchStatus

logger = structlog.get_logger(__name__)

AnswerFn = Callable[[QAFixture], Awaitable[CompletionResult]]


def keyword_coverage(answer: str, keywords: tuple[str, ...]) -> float:
    """Fraction of expected keywords present in the answer (case-insensitive).

    Refusal fixtures legitimately carry no keywords; callers must not grade
    them with this metric, so an empty tuple is a caller bug, not a 0.0.
    """
    if not keywords:
        raise ValueError("keyword_coverage requires at least one expected keyword")
    haystack = answer.casefold()
    hits = sum(1 for keyword in keywords if keyword.casefold() in haystack)
    return hits / len(keywords)


class EvalCaseResult(BaseModel):
    """Outcome of one fixture run."""

    model_config = ConfigDict(frozen=True)

    fixture_id: str
    answer: str
    keyword_coverage: float = Field(ge=0, le=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost: Decimal = Field(ge=Decimal(0))
    latency_ms: int = Field(ge=0)
    cached: bool


class EvaluationReport(BaseModel):
    """Aggregated run: per-case results plus token/cost/latency totals."""

    model_config = ConfigDict(frozen=True)

    fixture_version: str
    cases: tuple[EvalCaseResult, ...]
    mean_keyword_coverage: float = Field(ge=0, le=1)
    total_input_tokens: int = Field(ge=0)
    total_output_tokens: int = Field(ge=0)
    total_estimated_cost: Decimal = Field(ge=Decimal(0))
    mean_latency_ms: float = Field(ge=0)


class EvaluationHarness:
    """Drive an answer function over a fixture set and report telemetry.

    The answer function is the seam: tests plug in a fake provider, later
    milestones plug in the real RAG pipeline without changing the harness.
    """

    def __init__(self, answer_fn: AnswerFn) -> None:
        self._answer_fn = answer_fn

    async def run(
        self, fixtures: tuple[QAFixture, ...], *, fixture_version: str
    ) -> EvaluationReport:
        """Evaluate every fixture sequentially and aggregate the results."""
        refusal_ids = [fixture.fixture_id for fixture in fixtures if fixture.expect_refusal]
        if refusal_ids:
            raise ValueError(
                "EvaluationHarness grades keyword coverage only and cannot grade "
                f"expect_refusal fixtures {refusal_ids}; use RagEvaluationHarness."
            )
        cases: list[EvalCaseResult] = []
        for fixture in fixtures:
            result = await self._answer_fn(fixture)
            case = EvalCaseResult(
                fixture_id=fixture.fixture_id,
                answer=result.text,
                keyword_coverage=keyword_coverage(result.text, fixture.expected_keywords),
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                estimated_cost=result.estimated_cost,
                latency_ms=result.latency_ms,
                cached=result.cached,
            )
            cases.append(case)
            logger.info(
                "eval_case_completed",
                fixture_id=case.fixture_id,
                keyword_coverage=case.keyword_coverage,
                estimated_cost_usd=str(case.estimated_cost),
                latency_ms=case.latency_ms,
            )

        count = len(cases)
        report = EvaluationReport(
            fixture_version=fixture_version,
            cases=tuple(cases),
            mean_keyword_coverage=sum(case.keyword_coverage for case in cases) / count,
            total_input_tokens=sum(case.input_tokens for case in cases),
            total_output_tokens=sum(case.output_tokens for case in cases),
            total_estimated_cost=sum((case.estimated_cost for case in cases), start=Decimal(0)),
            mean_latency_ms=sum(case.latency_ms for case in cases) / count,
        )
        logger.info(
            "eval_run_completed",
            fixture_version=fixture_version,
            cases=count,
            mean_keyword_coverage=report.mean_keyword_coverage,
            total_estimated_cost_usd=str(report.total_estimated_cost),
        )
        return report


def section_hint_hit(hint: str, sections: tuple[str, ...]) -> bool:
    """Whether any retrieved section title matches the fixture's hint.

    Containment is checked in both directions after casefolding: parsed
    section titles carry numbering ("3 Model Architecture") while hints do
    not, and hints may name a subsection of a longer parsed title.
    """
    needle = hint.casefold().strip()
    for section in sections:
        candidate = section.casefold().strip()
        if candidate and (needle in candidate or candidate in needle):
            return True
    return False


class RagCaseOutcome(BaseModel):
    """What the RAG pipeline reports back for one fixture.

    Dense retrieval results and context anchors are reported separately so
    recall@k grades what the ANN search actually found; anchors are appended
    context, not retrieval hits. ``query_embedding_cost`` and
    ``pipeline_latency_ms`` are spend/latency incurred by this run, unlike
    the completion telemetry which may describe an earlier cached generation.
    """

    model_config = ConfigDict(frozen=True)

    answer: str
    refused: bool
    dense_sections: tuple[str, ...] = ()
    anchor_sections: tuple[str, ...] = ()
    source_match_status: QaSourceMatchStatus | None = None
    verified_citations: int = Field(default=0, ge=0)
    completion: CompletionResult | None = None
    query_embedding_cost: Decimal = Field(default=Decimal(0), ge=Decimal(0))
    pipeline_latency_ms: int = Field(default=0, ge=0)


RagAnswerFn = Callable[[QAFixture], Awaitable[RagCaseOutcome]]


class RagRunConfig(BaseModel):
    """Provenance of one evaluation run: everything needed to reproduce it."""

    model_config = ConfigDict(frozen=True)

    llm_provider: str
    llm_model: str
    prompt_version: str
    embedding_backend: str
    embedding_model: str
    retrieval_top_k: int = Field(ge=1)
    context_anchor_count: int = Field(ge=0)
    rerank_top_n: int = Field(ge=1)
    min_evidence_score: float = Field(ge=0, le=1)
    max_output_tokens: int = Field(ge=1)
    cache_enabled: bool
    qa_cache_ttl_seconds: int = Field(ge=1)


class RagCaseResult(BaseModel):
    """Graded outcome of one fixture run against the RAG pipeline.

    ``generation_*`` fields are metadata of the served completion: on a cache
    hit they describe the original generation, not spend incurred by this
    run. ``incremental_cost`` is what this run actually spent (query
    embedding plus generation only when uncached), and
    ``pipeline_latency_ms`` is this run's end-to-end wall clock.
    """

    model_config = ConfigDict(frozen=True)

    fixture_id: str
    answer: str
    refused: bool
    expect_refusal: bool
    refusal_correct: bool
    retrieval_hit: bool | None
    keyword_coverage: float | None = Field(default=None, ge=0, le=1)
    source_match_status: QaSourceMatchStatus | None
    verified_citations: int = Field(ge=0)
    generation_input_tokens: int = Field(ge=0)
    generation_output_tokens: int = Field(ge=0)
    generation_cost: Decimal = Field(ge=Decimal(0))
    generation_latency_ms: int = Field(ge=0)
    cached: bool
    query_embedding_cost: Decimal = Field(default=Decimal(0), ge=Decimal(0))
    incremental_cost: Decimal = Field(default=Decimal(0), ge=Decimal(0))
    pipeline_latency_ms: int = Field(default=0, ge=0)


class RagEvaluationReport(BaseModel):
    """Aggregated RAG run: quality rates plus token/cost/latency totals.

    Rates are ``None`` when the fixture set contains no case they apply to.
    ``source_match_rate`` counts only fully MATCHED answers; PARTIAL answers
    are reported separately and never folded into the headline rate.
    ``recall_at_k`` grades dense retrieval only -- context anchors never
    count as hits. Token totals and ``total_generation_cost`` aggregate
    completion metadata (cached hits report the original generation);
    ``total_incremental_cost`` is the spend this run actually incurred.
    """

    model_config = ConfigDict(frozen=True)

    fixture_version: str
    run_config: RagRunConfig | None = None
    cases: tuple[RagCaseResult, ...]
    recall_at_k: float | None = Field(default=None, ge=0, le=1)
    source_match_rate: float | None = Field(default=None, ge=0, le=1)
    partial_match_rate: float | None = Field(default=None, ge=0, le=1)
    citation_rate: float | None = Field(default=None, ge=0, le=1)
    refusal_accuracy: float | None = Field(default=None, ge=0, le=1)
    false_refusal_rate: float | None = Field(default=None, ge=0, le=1)
    mean_keyword_coverage: float | None = Field(default=None, ge=0, le=1)
    total_generation_input_tokens: int = Field(ge=0)
    total_generation_output_tokens: int = Field(ge=0)
    total_generation_cost: Decimal = Field(ge=Decimal(0))
    total_incremental_cost: Decimal = Field(ge=Decimal(0))
    mean_generation_latency_ms: float | None = Field(default=None, ge=0)
    mean_pipeline_latency_ms: float | None = Field(default=None, ge=0)


def _rate(hits: int, total: int) -> float | None:
    return hits / total if total else None


class RagEvaluationHarness:
    """Grade the full retrieval + grounded-answer pipeline over a fixture set.

    Unlike :class:`EvaluationHarness` (which only sees completion text), the
    answer function here reports retrieval and verification outcomes, so the
    report covers recall@k, source-match rate, citation rate, and refusal
    behavior alongside cost telemetry.
    """

    def __init__(self, answer_fn: RagAnswerFn) -> None:
        self._answer_fn = answer_fn

    async def run(
        self,
        fixtures: tuple[QAFixture, ...],
        *,
        fixture_version: str,
        run_config: RagRunConfig | None = None,
    ) -> RagEvaluationReport:
        """Evaluate every fixture sequentially and aggregate graded metrics."""
        cases: list[RagCaseResult] = []
        for fixture in fixtures:
            outcome = await self._answer_fn(fixture)
            completion = outcome.completion
            answerable = not fixture.expect_refusal
            generation_cost = completion.estimated_cost if completion else Decimal(0)
            cached = completion.cached if completion else False
            case = RagCaseResult(
                fixture_id=fixture.fixture_id,
                answer=outcome.answer,
                refused=outcome.refused,
                expect_refusal=fixture.expect_refusal,
                refusal_correct=outcome.refused == fixture.expect_refusal,
                retrieval_hit=(
                    section_hint_hit(fixture.section_hint, outcome.dense_sections)
                    if answerable and fixture.section_hint is not None
                    else None
                ),
                keyword_coverage=(
                    keyword_coverage(outcome.answer, fixture.expected_keywords)
                    if answerable and not outcome.refused
                    else None
                ),
                source_match_status=outcome.source_match_status,
                verified_citations=outcome.verified_citations,
                generation_input_tokens=completion.usage.input_tokens if completion else 0,
                generation_output_tokens=completion.usage.output_tokens if completion else 0,
                generation_cost=generation_cost,
                generation_latency_ms=completion.latency_ms if completion else 0,
                cached=cached,
                query_embedding_cost=outcome.query_embedding_cost,
                incremental_cost=outcome.query_embedding_cost
                + (Decimal(0) if cached else generation_cost),
                pipeline_latency_ms=outcome.pipeline_latency_ms,
            )
            cases.append(case)
            logger.info(
                "rag_eval_case_completed",
                fixture_id=case.fixture_id,
                refused=case.refused,
                refusal_correct=case.refusal_correct,
                retrieval_hit=case.retrieval_hit,
                keyword_coverage=case.keyword_coverage,
                source_match_status=(
                    case.source_match_status.value if case.source_match_status else None
                ),
                cached=case.cached,
                incremental_cost_usd=str(case.incremental_cost),
            )

        retrieval_cases = [case for case in cases if case.retrieval_hit is not None]
        answered = [case for case in cases if not case.expect_refusal and not case.refused]
        expected_refusals = [case for case in cases if case.expect_refusal]
        answerable = [case for case in cases if not case.expect_refusal]
        graded_coverage = [
            case.keyword_coverage for case in cases if case.keyword_coverage is not None
        ]
        generation_timed = [case for case in cases if case.generation_latency_ms > 0]
        pipeline_timed = [case for case in cases if case.pipeline_latency_ms > 0]

        report = RagEvaluationReport(
            fixture_version=fixture_version,
            run_config=run_config,
            cases=tuple(cases),
            recall_at_k=_rate(
                sum(1 for case in retrieval_cases if case.retrieval_hit), len(retrieval_cases)
            ),
            source_match_rate=_rate(
                sum(
                    1
                    for case in answered
                    if case.source_match_status is QaSourceMatchStatus.MATCHED
                ),
                len(answered),
            ),
            partial_match_rate=_rate(
                sum(
                    1
                    for case in answered
                    if case.source_match_status is QaSourceMatchStatus.PARTIAL
                ),
                len(answered),
            ),
            citation_rate=_rate(
                sum(1 for case in answered if case.verified_citations > 0), len(answered)
            ),
            refusal_accuracy=_rate(
                sum(1 for case in expected_refusals if case.refused), len(expected_refusals)
            ),
            false_refusal_rate=_rate(
                sum(1 for case in answerable if case.refused), len(answerable)
            ),
            mean_keyword_coverage=(
                sum(graded_coverage) / len(graded_coverage) if graded_coverage else None
            ),
            total_generation_input_tokens=sum(case.generation_input_tokens for case in cases),
            total_generation_output_tokens=sum(case.generation_output_tokens for case in cases),
            total_generation_cost=sum((case.generation_cost for case in cases), start=Decimal(0)),
            total_incremental_cost=sum((case.incremental_cost for case in cases), start=Decimal(0)),
            mean_generation_latency_ms=(
                sum(case.generation_latency_ms for case in generation_timed) / len(generation_timed)
                if generation_timed
                else None
            ),
            mean_pipeline_latency_ms=(
                sum(case.pipeline_latency_ms for case in pipeline_timed) / len(pipeline_timed)
                if pipeline_timed
                else None
            ),
        )
        logger.info(
            "rag_eval_run_completed",
            fixture_version=fixture_version,
            cases=len(cases),
            recall_at_k=report.recall_at_k,
            source_match_rate=report.source_match_rate,
            citation_rate=report.citation_rate,
            refusal_accuracy=report.refusal_accuracy,
            false_refusal_rate=report.false_refusal_rate,
            total_generation_cost_usd=str(report.total_generation_cost),
            total_incremental_cost_usd=str(report.total_incremental_cost),
        )
        return report
