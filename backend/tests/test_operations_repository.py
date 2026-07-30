"""Unit contracts for the bounded platform operations report."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.digest import DigestType
from mneme.models.job import JobStatus, PipelineStage
from mneme.models.paper import ParseQuality, ProcessingStatus
from mneme.repositories.operations import (
    PlatformOperationsRepository,
)

pytestmark = [pytest.mark.base, pytest.mark.db]


def _result(
    *,
    rows: list[tuple[object, ...]] | None = None,
    one: tuple[object, ...] | None = None,
    scalar: object | None = None,
) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows or []
    result.one.return_value = one
    result.scalar_one.return_value = scalar
    return result


def _repository_with_results(*results: MagicMock) -> tuple[PlatformOperationsRepository, AsyncMock]:
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = results
    return PlatformOperationsRepository(cast(AsyncSession, session)), session


def test_empty_snapshot_prefills_every_stable_enum_bucket() -> None:
    repository, session = _repository_with_results(
        _result(),
        _result(one=(0, 0, 0, 0)),
        _result(scalar=0),
        _result(),
        _result(),
        _result(),
    )
    local_time = datetime.fromisoformat("2026-07-30T20:00:00+08:00")

    snapshot = asyncio.run(
        repository.snapshot(
            now=local_time,
            window_hours=24,
            dispatch_lease_seconds=300,
            failed_limit=0,
        )
    )

    assert snapshot["schema_version"] == "platform-operations-v1"
    assert snapshot["generated_at"] == datetime(2026, 7, 30, 12, tzinfo=UTC)
    assert snapshot["window"] == {
        "start": datetime(2026, 7, 29, 12, tzinfo=UTC),
        "end": datetime(2026, 7, 30, 12, tzinfo=UTC),
        "hours": 24,
    }

    jobs = cast(dict[str, object], snapshot["jobs"])
    by_stage = cast(dict[str, dict[str, dict[str, int]]], jobs["by_stage_status"])
    assert set(by_stage) == {stage.value for stage in PipelineStage}
    for statuses in by_stage.values():
        assert set(statuses) == {status.value for status in JobStatus}
        assert all(value == {"count": 0, "attempts": 0} for value in statuses.values())
    assert jobs["recent_failures"] == []

    papers = cast(dict[str, object], snapshot["papers"])
    assert papers["by_processing_status"] == {status.value: 0 for status in ProcessingStatus}
    assert papers["latest_parse_quality"] == {
        **{quality.value: 0 for quality in ParseQuality},
        "not_parsed": 0,
    }
    digests = cast(dict[str, object], snapshot["digests"])
    assert digests["by_type"] == {digest_type.value: 0 for digest_type in DigestType}
    assert session.execute.await_count == 6


def test_snapshot_maps_counts_with_distinct_created_and_finished_windows() -> None:
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    failed_id = UUID("00000000-0000-0000-0000-000000000123")
    repository, session = _repository_with_results(
        _result(
            rows=[
                (PipelineStage.FETCH_METADATA, JobStatus.QUEUED, 2, 3),
                (PipelineStage.PARSE_PDF, JobStatus.FAILED, 1, 2),
            ]
        ),
        _result(one=(4, 1, 2, 1)),
        _result(scalar=1),
        _result(
            rows=[
                (
                    failed_id,
                    PipelineStage.PARSE_PDF,
                    "parse_failed",
                    2,
                    now - timedelta(days=2),
                    now - timedelta(minutes=5),
                    now - timedelta(minutes=4),
                )
            ]
        ),
        _result(
            rows=[
                (ProcessingStatus.READY, 3, 1),
                (ProcessingStatus.FAILED, 2, 0),
            ]
        ),
        _result(rows=[(ParseQuality.STRUCTURED, 2), (None, 3)]),
        _result(rows=[(DigestType.WEEKLY, 1)]),
    )

    snapshot = asyncio.run(
        repository.snapshot(
            now=now,
            window_hours=24,
            dispatch_lease_seconds=300,
            failed_limit=5,
        )
    )

    jobs = cast(dict[str, object], snapshot["jobs"])
    assert jobs["created"] == 3
    assert jobs["dispatch_attempts"] == 5
    assert jobs["queued"] == 4
    assert jobs["running"] == 1
    assert jobs["undispatched_queued"] == 2
    assert jobs["stale_dispatched_queued"] == 1
    assert jobs["failed"] == 1
    by_stage = cast(dict[str, dict[str, dict[str, int]]], jobs["by_stage_status"])
    assert by_stage["fetch_metadata"]["queued"] == {"count": 2, "attempts": 3}
    assert by_stage["parse_pdf"]["failed"] == {"count": 1, "attempts": 2}
    assert by_stage["download_pdf"]["succeeded"] == {"count": 0, "attempts": 0}

    failures = cast(list[dict[str, object]], jobs["recent_failures"])
    assert failures == [
        {
            "id": failed_id,
            "stage": "parse_pdf",
            "error_code": "parse_failed",
            "attempt_count": 2,
            "created_at": now - timedelta(days=2),
            "started_at": now - timedelta(minutes=5),
            "finished_at": now - timedelta(minutes=4),
        }
    ]
    assert set(failures[0]) == {
        "id",
        "stage",
        "error_code",
        "attempt_count",
        "created_at",
        "started_at",
        "finished_at",
    }

    papers = cast(dict[str, object], snapshot["papers"])
    assert papers["total"] == 5
    assert papers["created"] == 1
    assert cast(dict[str, int], papers["by_processing_status"])["partial"] == 0
    assert papers["latest_parse_quality"] == {
        "structured": 2,
        "text_only": 0,
        "abstract_only": 0,
        "not_parsed": 3,
    }
    assert snapshot["digests"] == {
        "generated": 1,
        "by_type": {"weekly": 1, "manual": 0},
    }

    statements = [call.args[0] for call in session.execute.await_args_list]
    job_sql = str(statements[0].compile(dialect=postgresql.dialect()))
    active_sql = str(statements[1].compile(dialect=postgresql.dialect()))
    failed_count_sql = str(statements[2].compile(dialect=postgresql.dialect()))
    failure_sql = str(statements[3].compile(dialect=postgresql.dialect()))
    paper_sql = str(statements[4].compile(dialect=postgresql.dialect()))
    quality_sql = str(statements[5].compile(dialect=postgresql.dialect()))
    digest_sql = str(statements[6].compile(dialect=postgresql.dialect()))

    assert "pipeline_jobs.created_at >=" in job_sql
    assert "pipeline_jobs.created_at <" in job_sql
    assert "GROUP BY pipeline_jobs.stage, pipeline_jobs.status" in job_sql
    assert "FILTER (WHERE pipeline_jobs.status =" in active_sql
    assert "pipeline_jobs.dispatched_at IS NULL" in active_sql
    assert "pipeline_jobs.dispatched_at <" in active_sql
    assert "pipeline_jobs.finished_at >=" in failed_count_sql
    assert "pipeline_jobs.finished_at <" in failed_count_sql
    assert "ORDER BY pipeline_jobs.finished_at DESC, pipeline_jobs.id DESC" in failure_sql
    assert "last_error" not in failure_sql
    assert "idempotency_key" not in failure_sql
    assert "papers.created_at >=" in paper_sql
    assert "DISTINCT ON (paper_versions.paper_id)" in quality_sql
    assert "LEFT OUTER JOIN" in quality_sql
    assert "digests.generated_at >=" in digest_sql
