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
    """Fraction of expected keywords present in the answer (case-insensitive)."""
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
    """What the RAG pipeline reports back for one fixture."""

    model_config = ConfigDict(frozen=True)

    answer: str
    refused: bool
    retrieved_sections: tuple[str, ...] = ()
    source_match_status: QaSourceMatchStatus | None = None
    verified_citations: int = Field(default=0, ge=0)
    completion: CompletionResult | None = None


RagAnswerFn = Callable[[QAFixture], Awaitable[RagCaseOutcome]]


class RagCaseResult(BaseModel):
    """Graded outcome of one fixture run against the RAG pipeline."""

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
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost: Decimal = Field(ge=Decimal(0))
    latency_ms: int = Field(ge=0)
    cached: bool


class RagEvaluationReport(BaseModel):
    """Aggregated RAG run: quality rates plus token/cost/latency totals.

    Rates are ``None`` when the fixture set contains no case they apply to.
    ``source_match_rate`` counts only fully MATCHED answers; PARTIAL answers
    are reported separately and never folded into the headline rate.
    """

    model_config = ConfigDict(frozen=True)

    fixture_version: str
    cases: tuple[RagCaseResult, ...]
    recall_at_k: float | None = Field(default=None, ge=0, le=1)
    source_match_rate: float | None = Field(default=None, ge=0, le=1)
    partial_match_rate: float | None = Field(default=None, ge=0, le=1)
    citation_rate: float | None = Field(default=None, ge=0, le=1)
    refusal_accuracy: float | None = Field(default=None, ge=0, le=1)
    false_refusal_rate: float | None = Field(default=None, ge=0, le=1)
    mean_keyword_coverage: float | None = Field(default=None, ge=0, le=1)
    total_input_tokens: int = Field(ge=0)
    total_output_tokens: int = Field(ge=0)
    total_estimated_cost: Decimal = Field(ge=Decimal(0))
    mean_latency_ms: float | None = Field(default=None, ge=0)


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
        self, fixtures: tuple[QAFixture, ...], *, fixture_version: str
    ) -> RagEvaluationReport:
        """Evaluate every fixture sequentially and aggregate graded metrics."""
        cases: list[RagCaseResult] = []
        for fixture in fixtures:
            outcome = await self._answer_fn(fixture)
            completion = outcome.completion
            answerable = not fixture.expect_refusal
            case = RagCaseResult(
                fixture_id=fixture.fixture_id,
                answer=outcome.answer,
                refused=outcome.refused,
                expect_refusal=fixture.expect_refusal,
                refusal_correct=outcome.refused == fixture.expect_refusal,
                retrieval_hit=(
                    section_hint_hit(fixture.section_hint, outcome.retrieved_sections)
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
                input_tokens=completion.usage.input_tokens if completion else 0,
                output_tokens=completion.usage.output_tokens if completion else 0,
                estimated_cost=completion.estimated_cost if completion else Decimal(0),
                latency_ms=completion.latency_ms if completion else 0,
                cached=completion.cached if completion else False,
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
                estimated_cost_usd=str(case.estimated_cost),
            )

        retrieval_cases = [case for case in cases if case.retrieval_hit is not None]
        answered = [case for case in cases if not case.expect_refusal and not case.refused]
        expected_refusals = [case for case in cases if case.expect_refusal]
        answerable = [case for case in cases if not case.expect_refusal]
        graded_coverage = [
            case.keyword_coverage for case in cases if case.keyword_coverage is not None
        ]
        timed = [case for case in cases if case.latency_ms > 0]

        report = RagEvaluationReport(
            fixture_version=fixture_version,
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
            total_input_tokens=sum(case.input_tokens for case in cases),
            total_output_tokens=sum(case.output_tokens for case in cases),
            total_estimated_cost=sum((case.estimated_cost for case in cases), start=Decimal(0)),
            mean_latency_ms=(
                sum(case.latency_ms for case in timed) / len(timed) if timed else None
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
            total_estimated_cost_usd=str(report.total_estimated_cost),
        )
        return report
