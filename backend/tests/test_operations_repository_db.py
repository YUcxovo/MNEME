"""PostgreSQL integration coverage for the platform operations report."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete

from mneme.db.session import Database
from mneme.models.digest import Digest, DigestType
from mneme.models.job import JobStatus, PipelineJob, PipelineStage
from mneme.models.paper import Paper, PaperVersion, ParseQuality, ProcessingStatus
from mneme.models.user import User
from mneme.repositories.operations import PlatformOperationsRepository

DATABASE_URL = os.getenv("MNEME_DATABASE_URL", "")
BACKEND_ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.db

if not DATABASE_URL:
    pytest.skip(
        "MNEME_DATABASE_URL is not configured for PostgreSQL integration tests",
        allow_module_level=True,
    )


@pytest.fixture(scope="module", autouse=True)
def upgrade_database() -> None:
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")


async def _snapshot(database: Database, now: datetime) -> dict[str, object]:
    async with database.session_factory() as session:
        return await PlatformOperationsRepository(session).snapshot(
            now=now,
            window_hours=24,
            dispatch_lease_seconds=300,
            failed_limit=100,
        )


async def _exercise_snapshot() -> None:
    database = Database(DATABASE_URL)
    suffix = uuid4().hex
    now = datetime(2199, 1, 2, 12, tzinfo=UTC)
    recent = now - timedelta(hours=1)
    old = now - timedelta(hours=25)
    user_id, ready_paper_id, old_paper_id = uuid4(), uuid4(), uuid4()
    queued_job_id, stale_job_id, failed_job_id = uuid4(), uuid4(), uuid4()
    job_ids = (queued_job_id, stale_job_id, failed_job_id)
    paper_ids = (ready_paper_id, old_paper_id)
    private_error = f"private-worker-detail-{suffix}"
    private_identity = f"private-job-identity-{suffix}"

    try:
        baseline = await _snapshot(database, now)
        async with database.session_factory() as session, session.begin():
            session.add(User(id=user_id, display_name=f"Operations User {suffix}"))
            session.add_all(
                [
                    Paper(
                        id=ready_paper_id,
                        arxiv_id=f"ops.{suffix}.1",
                        title="Recent operations paper",
                        abstract="Recent report fixture.",
                        primary_category="test.ops",
                        categories=["test.ops"],
                        pdf_url=f"https://arxiv.org/pdf/ops.{suffix}.1",
                        processing_status=ProcessingStatus.READY,
                        published_at=recent,
                        source_updated_at=recent,
                        created_at=recent,
                        updated_at=recent,
                    ),
                    Paper(
                        id=old_paper_id,
                        arxiv_id=f"ops.{suffix}.2",
                        title="Older operations paper",
                        abstract="Outside-window report fixture.",
                        primary_category="test.ops",
                        categories=["test.ops"],
                        pdf_url=f"https://arxiv.org/pdf/ops.{suffix}.2",
                        processing_status=ProcessingStatus.FAILED,
                        published_at=old,
                        source_updated_at=old,
                        created_at=old,
                        updated_at=old,
                    ),
                    PaperVersion(
                        paper_id=ready_paper_id,
                        version_number=1,
                        parsed_checksum="a" * 64,
                        parser_version="ops-test-v1",
                        parse_quality=ParseQuality.STRUCTURED,
                        parsed_at=recent,
                        created_at=recent,
                    ),
                ]
            )
            session.add_all(
                [
                    PipelineJob(
                        id=queued_job_id,
                        idempotency_key=f"ops-{suffix}-undispatched",
                        stage=PipelineStage.FETCH_METADATA,
                        status=JobStatus.QUEUED,
                        attempt_count=0,
                        pipeline_version="ops-test-v1",
                        created_at=recent,
                        updated_at=recent,
                    ),
                    PipelineJob(
                        id=stale_job_id,
                        idempotency_key=f"ops-{suffix}-stale",
                        stage=PipelineStage.FETCH_METADATA,
                        status=JobStatus.QUEUED,
                        attempt_count=1,
                        pipeline_version="ops-test-v1",
                        dispatched_at=now - timedelta(minutes=10),
                        created_at=recent,
                        updated_at=recent,
                    ),
                    PipelineJob(
                        id=failed_job_id,
                        idempotency_key=private_identity,
                        stage=PipelineStage.PARSE_PDF,
                        status=JobStatus.FAILED,
                        attempt_count=2,
                        error_code="ops_fixture_failed",
                        last_error=private_error,
                        pipeline_version="ops-test-v1",
                        started_at=now - timedelta(minutes=20),
                        finished_at=now - timedelta(minutes=10),
                        created_at=old,
                        updated_at=now - timedelta(minutes=10),
                    ),
                    Digest(
                        user_id=user_id,
                        digest_type=DigestType.WEEKLY,
                        generated_at=recent,
                        preference_model_version=1,
                        generator_version="ops-test-v1",
                    ),
                ]
            )

        report = await _snapshot(database, now)
        baseline_jobs = cast(dict[str, object], baseline["jobs"])
        jobs = cast(dict[str, object], report["jobs"])
        expected_job_deltas = {
            "created": 2,
            "dispatch_attempts": 1,
            "queued": 2,
            "undispatched_queued": 1,
            "stale_dispatched_queued": 1,
            "failed": 1,
        }
        for key, delta in expected_job_deltas.items():
            assert cast(int, jobs[key]) == cast(int, baseline_jobs[key]) + delta
        failures = cast(list[dict[str, object]], jobs["recent_failures"])
        failure = next(item for item in failures if item["id"] == failed_job_id)
        assert failure["error_code"] == "ops_fixture_failed"
        assert private_error not in str(report)
        assert private_identity not in str(report)

        baseline_papers = cast(dict[str, object], baseline["papers"])
        papers = cast(dict[str, object], report["papers"])
        assert papers["total"] == cast(int, baseline_papers["total"]) + 2
        assert papers["created"] == cast(int, baseline_papers["created"]) + 1
        baseline_quality = cast(dict[str, int], baseline_papers["latest_parse_quality"])
        quality = cast(dict[str, int], papers["latest_parse_quality"])
        assert quality["structured"] == baseline_quality["structured"] + 1
        assert quality["not_parsed"] == baseline_quality["not_parsed"] + 1

        baseline_digests = cast(dict[str, object], baseline["digests"])
        digests = cast(dict[str, object], report["digests"])
        assert digests["generated"] == cast(int, baseline_digests["generated"]) + 1
    finally:
        async with database.session_factory() as session, session.begin():
            await session.execute(delete(PipelineJob).where(PipelineJob.id.in_(job_ids)))
            await session.execute(delete(User).where(User.id == user_id))
            await session.execute(delete(Paper).where(Paper.id.in_(paper_ids)))
        await database.dispose()


def test_platform_snapshot_uses_current_and_windowed_postgresql_state() -> None:
    asyncio.run(_exercise_snapshot())
