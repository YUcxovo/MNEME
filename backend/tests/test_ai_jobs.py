"""Error mapping and retry semantics of the ARQ AI job harness."""

import asyncio
from decimal import Decimal
from typing import Any, Self

import pytest

from mneme.ai.budget import BudgetExceededError
from mneme.ai.pipeline import PaperNotReadyError
from mneme.ai.types import LLMProviderError, ProviderNotConfiguredError
from mneme.tasks.ai_jobs import _run_stage


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
    outcome = asyncio.run(
        _run_stage(ctx, stage_name="test_stage", job_id=None, paper_id="p1", runner=runner)
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
