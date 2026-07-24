"""Evaluation harness: fixtures, scoring, RAG grading, and cost telemetry."""

from mneme.ai.evaluation.fixtures import QAFixture, load_qa_fixtures
from mneme.ai.evaluation.harness import (
    EvalCaseResult,
    EvaluationHarness,
    EvaluationReport,
    RagCaseOutcome,
    RagCaseResult,
    RagEvaluationHarness,
    RagEvaluationReport,
)

__all__ = [
    "EvalCaseResult",
    "EvaluationHarness",
    "EvaluationReport",
    "QAFixture",
    "RagCaseOutcome",
    "RagCaseResult",
    "RagEvaluationHarness",
    "RagEvaluationReport",
    "load_qa_fixtures",
]
