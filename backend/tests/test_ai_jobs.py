"""Error mapping and retry semantics of the ARQ AI job harness."""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Self
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from mneme.ai.budget import BudgetExceededError
from mneme.ai.pipeline import PaperNotReadyError
from mneme.ai.types import LLMProviderError, ProviderNotConfiguredError
from mneme.models.job import JobStatus, PipelineStage
from mneme.tasks import ai_runtime
from mneme.tasks.ai_runtime import run_ai_stage as _run_stage


class FakeSession:
    """Session stand-in tracking transaction outcomes."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class FakeDatabase:
    """Database stand-in producing one recorded fake session."""

    def __init__(self) -> None:
        self.session = FakeSession()

    def session_factory(self) -> FakeSession:
        return self.session


def _ctx() -> dict[str, Any]:
    return {"database": FakeDatabase()}


def _run(runner) -> tuple[str, FakeDatabase]:
    ctx = _ctx()
    paper_id = str(uuid4())
    version_id = str(uuid4())
    outcome = asyncio.run(
        _run_stage(
            ctx,
            stage=PipelineStage.SUMMARIZE_PAPER,
            job_id=None,
            paper_id=paper_id,
            paper_version_id=version_id,
            runner=runner,
        )
    )
    return outcome, ctx["database"]


@pytest.mark.base
@pytest.mark.pipeline
def test_successful_stage_commits_and_reports_ok() -> None:
    async def runner(session):
        return "done"

    outcome, database = _run(runner)

    assert outcome == "ok"
    assert database.session.commits == 1
    assert database.session.rollbacks == 0


@pytest.mark.base
@pytest.mark.pipeline
def test_budget_exhaustion_is_terminal_not_retried() -> None:
    async def runner(session):
        raise BudgetExceededError(spent_usd=Decimal("5"), cap_usd=Decimal("5"))

    outcome, database = _run(runner)

    assert outcome == "budget_exhausted"
    assert database.session.rollbacks == 1


@pytest.mark.base
@pytest.mark.pipeline
def test_retryable_provider_error_propagates_for_arq_retry() -> None:
    async def runner(session):
        raise LLMProviderError("rate limited", retryable=True)

    with pytest.raises(LLMProviderError):
        _run(runner)


@pytest.mark.base
@pytest.mark.pipeline
def test_terminal_provider_error_is_swallowed_after_recording() -> None:
    async def runner(session):
        raise LLMProviderError("bad request", retryable=False)

    outcome, _ = _run(runner)

    assert outcome == "provider_error"


@pytest.mark.base
@pytest.mark.pipeline
def test_unconfigured_provider_maps_to_stable_outcome() -> None:
    async def runner(session):
        raise ProviderNotConfiguredError("no key")

    outcome, _ = _run(runner)

    assert outcome == "provider_unconfigured"


@pytest.mark.base
@pytest.mark.pipeline
def test_missing_paper_maps_to_stable_outcome() -> None:
    async def runner(session):
        raise PaperNotReadyError("no such paper")

    outcome, _ = _run(runner)

    assert outcome == "paper_not_ready"


@pytest.mark.base
@pytest.mark.pipeline
def test_ai_stage_rejects_obsolete_pipeline_version(monkeypatch: pytest.MonkeyPatch) -> None:
    paper_id = uuid4()
    version_id = uuid4()
    job_id = uuid4()

    class FakeRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def get(self, requested_job_id: object) -> SimpleNamespace:
            assert requested_job_id == job_id
            return SimpleNamespace(
                stage=PipelineStage.SUMMARIZE_PAPER,
                paper_id=paper_id,
                paper_version_id=version_id,
                pipeline_version="obsolete",
                status=JobStatus.QUEUED,
            )

    monkeypatch.setattr(ai_runtime, "PipelineJobRepository", FakeRepository)
    runner = AsyncMock(return_value="unused")

    outcome = asyncio.run(
        _run_stage(
            _ctx(),
            stage=PipelineStage.SUMMARIZE_PAPER,
            job_id=str(job_id),
            paper_id=str(paper_id),
            paper_version_id=str(version_id),
            runner=runner,
        )
    )

    assert outcome == "pipeline_job_identity_mismatch"
    runner.assert_not_awaited()
