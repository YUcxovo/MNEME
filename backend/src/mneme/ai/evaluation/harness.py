"""Run fixtures through an answer function and aggregate quality/cost metrics."""

from collections.abc import Awaitable, Callable
from decimal import Decimal

import structlog
from pydantic import BaseModel, ConfigDict, Field

from mneme.ai.evaluation.fixtures import QAFixture
from mneme.ai.types import CompletionResult

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
