"""Acceptance-sequence tests for the deployed MVP smoke runner."""

import asyncio
from uuid import UUID

import pytest

from mneme.api.schemas.digests import Digest
from mneme.api.schemas.graphs import Graph
from mneme.api.schemas.jobs import Job
from mneme.api.schemas.papers import Paper, PaperPage
from mneme.api.schemas.preferences import Preferences
from mneme.api.schemas.qa import Answer
from mneme.api.schemas.summaries import Summary
from mneme.demo.smoke import run_mvp_smoke
from mneme.demo.smoke_client import LivenessPayload, ReadinessPayload
from mneme.demo.smoke_types import MvpSmokeConfig

PAPER_ID = UUID("00000000-0000-4000-8000-000000000001")
NEIGHBOR_ID = UUID("00000000-0000-4000-8000-000000000002")
JOB_ID = UUID("00000000-0000-4000-8000-000000000003")


def _paper() -> Paper:
    return Paper.model_validate(
        {
            "id": str(PAPER_ID),
            "arxiv_id": "1706.03762",
            "title": "Attention Is All You Need",
            "authors": ["A. Author"],
            "abstract": "A test abstract.",
            "primary_category": "cs.CL",
            "categories": ["cs.CL"],
            "pdf_url": "https://arxiv.org/pdf/1706.03762",
            "source_license": None,
            "processing_status": "ready",
            "published_at": "2017-06-12T00:00:00Z",
            "updated_at": "2017-06-12T00:00:00Z",
        }
    )


class FakeSmokeClient:
    """Small deterministic implementation of the public smoke operations."""

    def __init__(self, *, failed_job: bool = False, connected_graph: bool = True) -> None:
        self.failed_job = failed_job
        self.connected_graph = connected_graph
        self.summary_calls = 0
        self.qa_calls = 0
        self.closed = False

    async def liveness(self) -> LivenessPayload:
        return LivenessPayload(status="ok")

    async def readiness(self) -> ReadinessPayload:
        return ReadinessPayload.model_validate(
            {"status": "ready", "dependencies": {"postgresql": "ready", "redis": "ready"}}
        )

    async def preferences(self) -> Preferences:
        return Preferences(
            topics=["machine learning"], followed_authors=[], model_version=2, updated_at=None
        )

    async def papers(self, *, cursor: str | None = None) -> PaperPage:
        assert cursor is None
        return PaperPage(items=[_paper()])

    async def summary(self, paper_id: UUID) -> Summary | Job:
        assert paper_id == PAPER_ID
        self.summary_calls += 1
        if self.summary_calls == 1:
            return Job(
                id=JOB_ID,
                stage="summarize_paper",
                status="failed" if self.failed_job else "succeeded",
            )
        return Summary(
            paper_id=PAPER_ID,
            status="ready",
            tldr="A source-grounded summary.",
            key_claims=["A claim"],
            source_match_status="matched",
        )

    async def job(self, job_id: UUID) -> Job:
        raise AssertionError(f"terminal job {job_id} should not be polled")

    async def recommended_digest(self) -> Digest:
        return Digest.model_validate(
            {
                "id": "00000000-0000-4000-8000-000000000004",
                "digest_type": "weekly",
                "generated_at": "2026-08-03T00:00:00Z",
                "entries": [
                    {
                        "paper": _paper().model_dump(mode="json"),
                        "rank": 1,
                        "relevance_score": 0.9,
                        "recommendation_reason": "Matches the configured topic.",
                    }
                ],
            }
        )

    async def graph(self, paper_id: UUID) -> Graph:
        assert paper_id == PAPER_ID
        nodes = [{"id": str(PAPER_ID), "title": "Center"}]
        edges: list[dict[str, str]] = []
        if self.connected_graph:
            nodes.append({"id": str(NEIGHBOR_ID), "title": "Neighbor"})
            edges.append({"source": str(PAPER_ID), "target": str(NEIGHBOR_ID)})
        return Graph.model_validate(
            {
                "center_id": str(PAPER_ID),
                "nodes": nodes,
                "edges": edges,
                "algorithm_status": "ready",
                "graph_version": "test-v1",
            }
        )

    async def ask(self, paper_id: UUID, question: str) -> Answer:
        assert paper_id == PAPER_ID
        assert question == "What method does this paper propose?"
        self.qa_calls += 1
        return Answer.model_validate(
            {
                "answer": "It proposes a source-grounded method.",
                "citations": [
                    {
                        "paper_id": str(PAPER_ID),
                        "arxiv_id": "1706.03762",
                        "section_title": "Method",
                        "chunk_id": "00000000-0000-4000-8000-000000000005",
                        "source_match": True,
                    }
                ],
                "source_match_status": "matched",
                "conversation_id": "00000000-0000-4000-8000-000000000006",
            }
        )

    async def aclose(self) -> None:
        self.closed = True


def _config(*, question: str | None = None) -> MvpSmokeConfig:
    return MvpSmokeConfig(base_url="https://demo.example", question=question)


@pytest.mark.base
def test_mvp_smoke_passes_core_loop_and_optional_qa() -> None:
    client = FakeSmokeClient()
    report = asyncio.run(
        run_mvp_smoke(
            _config(question="What method does this paper propose?"),
            token="token",
            client=client,
        )
    )

    assert report.status == "passed"
    assert [check.name for check in report.checks] == [
        "liveness",
        "readiness",
        "preferences",
        "catalog",
        "summary",
        "digest",
        "graph",
        "qa",
    ]
    assert all(check.status == "passed" for check in report.checks)
    assert client.qa_calls == 1
    assert client.closed


@pytest.mark.base
def test_mvp_smoke_skips_qa_only_when_question_is_absent() -> None:
    client = FakeSmokeClient()
    report = asyncio.run(run_mvp_smoke(_config(), token="token", client=client))

    assert report.status == "passed"
    assert report.checks[-1].as_dict() == {
        "details": {"reason": "question_not_configured"},
        "name": "qa",
        "status": "skipped",
    }
    assert client.qa_calls == 0


@pytest.mark.base
def test_mvp_smoke_fails_on_terminal_summary_job() -> None:
    report = asyncio.run(
        run_mvp_smoke(_config(), token="token", client=FakeSmokeClient(failed_job=True))
    )

    assert report.status == "failed"
    assert report.checks[-1].name == "summary"
    assert report.checks[-1].details == {
        "code": "summary_job_failed",
        "operation": "job",
    }


@pytest.mark.base
def test_mvp_smoke_requires_connected_graph() -> None:
    report = asyncio.run(
        run_mvp_smoke(_config(), token="token", client=FakeSmokeClient(connected_graph=False))
    )

    assert report.status == "failed"
    assert report.checks[-1].name == "graph"
    assert report.checks[-1].details == {"code": "graph_not_connected"}


@pytest.mark.base
def test_mvp_smoke_converts_timeout_to_stable_failure() -> None:
    class TimeoutClient(FakeSmokeClient):
        async def liveness(self) -> LivenessPayload:
            raise TimeoutError

    report = asyncio.run(run_mvp_smoke(_config(), token="token", client=TimeoutClient()))

    assert report.status == "failed"
    assert report.checks[-1].as_dict() == {
        "details": {"code": "smoke_deadline_exceeded"},
        "name": "liveness",
        "status": "failed",
    }
