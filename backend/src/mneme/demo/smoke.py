"""Public-API acceptance sequence for a deployed Mneme MVP."""

from __future__ import annotations

import asyncio
from typing import Protocol
from uuid import UUID

from mneme.api.schemas.digests import Digest
from mneme.api.schemas.graphs import Graph
from mneme.api.schemas.jobs import Job
from mneme.api.schemas.papers import Paper, PaperPage
from mneme.api.schemas.preferences import Preferences
from mneme.api.schemas.qa import Answer
from mneme.api.schemas.summaries import Summary
from mneme.demo.smoke_client import LivenessPayload, MvpSmokeClient, ReadinessPayload
from mneme.demo.smoke_types import (
    MvpSmokeConfig,
    MvpSmokeError,
    MvpSmokeReport,
    SmokeCheck,
)
from mneme.models.job import JobStatus
from mneme.models.paper import ProcessingStatus
from mneme.models.qa import QaSourceMatchStatus


class MvpSmokeOperations(Protocol):
    """Public operations exercised by the deployment acceptance sequence."""

    async def liveness(self) -> LivenessPayload: ...

    async def readiness(self) -> ReadinessPayload: ...

    async def preferences(self) -> Preferences: ...

    async def papers(self, *, cursor: str | None = None) -> PaperPage: ...

    async def paper(self, paper_id: UUID) -> Paper: ...

    async def summary(self, paper_id: UUID) -> Summary | Job: ...

    async def job(self, job_id: UUID) -> Job: ...

    async def recommended_digest(self) -> Digest: ...

    async def graph(self, paper_id: UUID) -> Graph: ...

    async def ask(self, paper_id: UUID, question: str) -> Answer: ...

    async def aclose(self) -> None: ...


async def run_mvp_smoke(
    config: MvpSmokeConfig,
    *,
    token: str,
    client: MvpSmokeOperations | None = None,
) -> MvpSmokeReport:
    """Run the public core loop and return a credential-free report."""
    resolved_client = client or MvpSmokeClient(
        base_url=config.base_url,
        token=token,
        timeout_seconds=config.request_timeout_seconds,
    )
    checks: list[SmokeCheck] = []
    current_check = "liveness"
    try:
        async with asyncio.timeout(config.deadline_seconds):
            liveness = await resolved_client.liveness()
            _require(liveness.status == "ok", current_check, "unexpected_liveness")
            checks.append(_passed(current_check))

            current_check = "readiness"
            readiness = await resolved_client.readiness()
            _require(
                readiness.status == "ready"
                and readiness.dependencies.postgresql == "ready"
                and readiness.dependencies.redis == "ready",
                current_check,
                "dependencies_not_ready",
            )
            checks.append(
                _passed(
                    current_check,
                    postgresql=readiness.dependencies.postgresql,
                    redis=readiness.dependencies.redis,
                )
            )

            current_check = "preferences"
            preferences = await resolved_client.preferences()
            _require(bool(preferences.topics), current_check, "preferences_empty")
            checks.append(
                _passed(
                    current_check,
                    topic_count=len(preferences.topics),
                    followed_author_count=len(preferences.followed_authors),
                )
            )

            current_check = "catalog"
            paper, scanned = await _find_seed_paper(resolved_client, config)
            _require(
                paper.processing_status is ProcessingStatus.READY,
                current_check,
                "seed_paper_not_ready",
            )
            checks.append(
                _passed(
                    current_check,
                    catalog_items_scanned=scanned,
                    processing_status=paper.processing_status.value,
                )
            )

            current_check = "summary"
            summary, completed_jobs = await _resolve_summary(resolved_client, paper.id, config)
            _require(summary.paper_id == paper.id, current_check, "summary_paper_mismatch")
            _require(bool(summary.tldr.strip()), current_check, "summary_empty")
            checks.append(
                _passed(
                    current_check,
                    completed_jobs=completed_jobs,
                    source_match_status=summary.source_match_status.value,
                    summary_status=summary.status.value,
                )
            )

            current_check = "digest"
            digest = await resolved_client.recommended_digest()
            _require(bool(digest.entries), current_check, "digest_empty")
            checks.append(_passed(current_check, entry_count=len(digest.entries)))

            current_check = "graph"
            graph = await resolved_client.graph(paper.id)
            _require(graph.center_id == paper.id, current_check, "graph_center_mismatch")
            _require(
                len(graph.nodes) >= config.minimum_graph_nodes
                and len(graph.edges) >= config.minimum_graph_edges,
                current_check,
                "graph_not_connected",
            )
            checks.append(
                _passed(
                    current_check,
                    algorithm_status=graph.algorithm_status,
                    edge_count=len(graph.edges),
                    node_count=len(graph.nodes),
                )
            )

            current_check = "qa"
            if config.question is None:
                checks.append(
                    SmokeCheck(
                        name=current_check,
                        status="skipped",
                        details={"reason": "question_not_configured"},
                    )
                )
            else:
                answer = await resolved_client.ask(paper.id, config.question.strip())
                _require(bool(answer.answer.strip()), current_check, "answer_empty")
                _require(
                    answer.source_match_status is QaSourceMatchStatus.MATCHED
                    and bool(answer.citations)
                    and all(citation.source_match for citation in answer.citations),
                    current_check,
                    "answer_not_source_matched",
                )
                _require(
                    all(
                        citation.paper_id == paper.id and citation.arxiv_id == paper.arxiv_id
                        for citation in answer.citations
                    ),
                    current_check,
                    "answer_citation_identity_mismatch",
                )
                checks.append(
                    _passed(
                        current_check,
                        citation_count=len(answer.citations),
                        source_match_status=answer.source_match_status.value,
                    )
                )
    except MvpSmokeError as error:
        checks.append(SmokeCheck(current_check, "failed", error.safe_details()))
    except TimeoutError:
        checks.append(SmokeCheck(current_check, "failed", {"code": "smoke_deadline_exceeded"}))
    except Exception:
        checks.append(SmokeCheck(current_check, "failed", {"code": "unexpected_failure"}))
    finally:
        try:
            await resolved_client.aclose()
        except Exception:
            if not any(check.status == "failed" for check in checks):
                checks.append(SmokeCheck("client_close", "failed", {"code": "client_close_failed"}))
    return MvpSmokeReport(seed_arxiv_id=config.seed_arxiv_id, checks=tuple(checks))


async def _find_seed_paper(client: MvpSmokeOperations, config: MvpSmokeConfig) -> tuple[Paper, int]:
    if config.seed_paper_id is not None:
        paper = await client.paper(config.seed_paper_id)
        if paper.arxiv_id != config.seed_arxiv_id:
            raise MvpSmokeError("catalog", "seed_paper_identity_mismatch")
        return paper, 1
    cursor: str | None = None
    observed_cursors: set[str] = set()
    scanned = 0
    for _page_number in range(config.maximum_catalog_pages):
        page = await client.papers(cursor=cursor)
        scanned += len(page.items)
        for paper in page.items:
            if paper.arxiv_id == config.seed_arxiv_id:
                return paper, scanned
        if page.next_cursor is None:
            break
        if page.next_cursor in observed_cursors:
            raise MvpSmokeError("catalog", "catalog_cursor_repeated")
        observed_cursors.add(page.next_cursor)
        cursor = page.next_cursor
    raise MvpSmokeError("catalog", "seed_paper_missing")


async def _resolve_summary(
    client: MvpSmokeOperations, paper_id: UUID, config: MvpSmokeConfig
) -> tuple[Summary, int]:
    for completed_jobs in range(config.maximum_summary_jobs + 1):
        result = await client.summary(paper_id)
        if isinstance(result, Summary):
            return result, completed_jobs
        if completed_jobs >= config.maximum_summary_jobs:
            raise MvpSmokeError("summary", "summary_job_limit_exceeded")
        await _wait_for_job(client, result, config.poll_interval_seconds)
    raise MvpSmokeError("summary", "summary_job_limit_exceeded")


async def _wait_for_job(client: MvpSmokeOperations, job: Job, poll_interval_seconds: float) -> None:
    current = job
    while current.status not in {JobStatus.SUCCEEDED, JobStatus.FAILED}:
        await asyncio.sleep(poll_interval_seconds)
        current = await client.job(current.id)
    if current.status is JobStatus.FAILED:
        raise MvpSmokeError("summary", "summary_job_failed", operation="job")


def _require(condition: bool, check: str, code: str) -> None:
    if not condition:
        raise MvpSmokeError(check, code)


def _passed(name: str, **details: str | int | bool) -> SmokeCheck:
    return SmokeCheck(name=name, status="passed", details=details)
