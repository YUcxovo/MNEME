"""Gated PostgreSQL tests for race-safe durable pipeline-job creation."""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, select

from mneme.db.session import Database
from mneme.models.job import JobStatus, PipelineJob, PipelineStage
from mneme.models.paper import Paper, PaperVersion, ProcessingStatus
from mneme.repositories.job_identity import (
    PipelineJobIdentityConflictError,
    build_job_idempotency_key,
)
from mneme.repositories.jobs import PipelineJobRepository

DATABASE_URL = os.getenv("MNEME_DATABASE_URL", "")
BACKEND_ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.db, pytest.mark.pipeline]

if not DATABASE_URL:
    pytest.skip(
        "MNEME_DATABASE_URL is not configured for PostgreSQL integration tests",
        allow_module_level=True,
    )


@pytest.fixture(scope="module", autouse=True)
def upgrade_database() -> None:
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")


async def _add_paper(database: Database) -> tuple[UUID, UUID, UUID]:
    paper_id = uuid4()
    first_version_id = uuid4()
    second_version_id = uuid4()
    now = datetime.now(UTC)
    async with database.session_factory() as session, session.begin():
        session.add(
            Paper(
                id=paper_id,
                arxiv_id=f"job-test.{uuid4().hex}",
                title="Pipeline identity fixture",
                abstract="A fixture paper for durable pipeline-job tests.",
                primary_category="cs.AI",
                categories=["cs.AI"],
                pdf_url="https://arxiv.org/pdf/job-test",
                source_license=None,
                processing_status=ProcessingStatus.METADATA_ONLY,
                published_at=now,
                source_updated_at=now,
            )
        )
        session.add_all(
            [
                PaperVersion(
                    id=first_version_id,
                    paper_id=paper_id,
                    version_number=1,
                    submitted_at=now,
                ),
                PaperVersion(
                    id=second_version_id,
                    paper_id=paper_id,
                    version_number=2,
                    submitted_at=now,
                ),
            ]
        )
    return paper_id, first_version_id, second_version_id


async def _delete_paper(database: Database, paper_id: UUID) -> None:
    async with database.session_factory() as session, session.begin():
        await session.execute(delete(Paper).where(Paper.id == paper_id))


def _summary_key(paper_id: UUID, version_id: UUID) -> str:
    return build_job_idempotency_key(
        stage=PipelineStage.SUMMARIZE_PAPER,
        scope={"paper_id": paper_id, "paper_version_id": version_id},
        inputs={"input_checksum": "a" * 64},
    )


async def _exercise_concurrent_creation() -> None:
    database = Database(DATABASE_URL)
    paper_id, version_id, next_version_id = await _add_paper(database)
    key = _summary_key(paper_id, version_id)

    async def create() -> tuple[UUID, bool]:
        async with database.session_factory() as session:
            job, created = await PipelineJobRepository(session).get_or_create(
                idempotency_key=key,
                stage=PipelineStage.SUMMARIZE_PAPER,
                paper_id=paper_id,
                paper_version_id=version_id,
            )
            await session.commit()
            return job.id, created

    try:
        results = await asyncio.gather(create(), create())
        assert {job_id for job_id, _ in results} == {results[0][0]}
        assert sorted(created for _, created in results) == [False, True]

        async with database.session_factory() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(PipelineJob)
                .where(PipelineJob.idempotency_key == key)
            )
            next_job, created = await PipelineJobRepository(session).get_or_create(
                idempotency_key=_summary_key(paper_id, next_version_id),
                stage=PipelineStage.SUMMARIZE_PAPER,
                paper_id=paper_id,
                paper_version_id=next_version_id,
            )
            await session.commit()

        assert count == 1
        assert created is True
        assert next_job.id not in {job_id for job_id, _ in results}
    finally:
        await _delete_paper(database, paper_id)
        await database.dispose()


def test_concurrent_creators_share_one_revision_scoped_job() -> None:
    asyncio.run(_exercise_concurrent_creation())


async def _exercise_conflicting_stored_identity() -> None:
    database = Database(DATABASE_URL)
    paper_id, requested_version_id, stored_version_id = await _add_paper(database)
    key = _summary_key(paper_id, requested_version_id)

    try:
        async with database.session_factory() as session, session.begin():
            session.add(
                PipelineJob(
                    paper_id=paper_id,
                    paper_version_id=stored_version_id,
                    idempotency_key=key,
                    stage=PipelineStage.SUMMARIZE_PAPER,
                    status=JobStatus.QUEUED,
                    pipeline_version="v1",
                )
            )

        async with database.session_factory() as session:
            with pytest.raises(PipelineJobIdentityConflictError) as captured:
                await PipelineJobRepository(session).get_or_create(
                    idempotency_key=key,
                    stage=PipelineStage.SUMMARIZE_PAPER,
                    paper_id=paper_id,
                    paper_version_id=requested_version_id,
                )
            assert captured.value.code == "pipeline_job_identity_conflict"
    finally:
        await _delete_paper(database, paper_id)
        await database.dispose()


def test_conflicting_stored_identity_raises_stable_error() -> None:
    asyncio.run(_exercise_conflicting_stored_identity())


async def _exercise_scope_validation() -> None:
    database = Database(DATABASE_URL)
    try:
        async with database.session_factory() as session:
            key = build_job_idempotency_key(
                stage=PipelineStage.SUMMARIZE_PAPER,
                scope={"paper_id": uuid4()},
                inputs={},
            )
            with pytest.raises(ValueError, match="paper and paper-version"):
                await PipelineJobRepository(session).get_or_create(
                    idempotency_key=key,
                    stage=PipelineStage.SUMMARIZE_PAPER,
                    paper_id=uuid4(),
                    paper_version_id=None,
                )
    finally:
        await database.dispose()


def test_revision_scoped_stage_requires_both_resource_ids() -> None:
    asyncio.run(_exercise_scope_validation())


async def _exercise_latest_failed_selection() -> None:
    database = Database(DATABASE_URL)
    paper_id, old_version_id, latest_version_id = await _add_paper(database)
    old_job_id, latest_job_id, succeeded_job_id = uuid4(), uuid4(), uuid4()
    try:
        async with database.session_factory() as session, session.begin():
            session.add_all(
                [
                    PipelineJob(
                        id=old_job_id,
                        paper_id=paper_id,
                        paper_version_id=old_version_id,
                        idempotency_key=f"failed-old-{uuid4().hex}",
                        stage=PipelineStage.SUMMARIZE_PAPER,
                        status=JobStatus.FAILED,
                        pipeline_version="v1",
                    ),
                    PipelineJob(
                        id=latest_job_id,
                        paper_id=paper_id,
                        paper_version_id=latest_version_id,
                        idempotency_key=f"failed-latest-{uuid4().hex}",
                        stage=PipelineStage.SUMMARIZE_PAPER,
                        status=JobStatus.FAILED,
                        pipeline_version="v1",
                    ),
                    PipelineJob(
                        id=succeeded_job_id,
                        paper_id=paper_id,
                        paper_version_id=latest_version_id,
                        idempotency_key=f"succeeded-latest-{uuid4().hex}",
                        stage=PipelineStage.CHUNK_PAPER,
                        status=JobStatus.SUCCEEDED,
                        pipeline_version="v1",
                    ),
                ]
            )

        async with database.session_factory() as session:
            jobs = await PipelineJobRepository(session).list_failed_latest_revision_jobs(
                (paper_id,)
            )

        assert [job.id for job in jobs] == [latest_job_id]
    finally:
        await _delete_paper(database, paper_id)
        await database.dispose()


def test_failed_retry_selection_uses_only_latest_revision() -> None:
    asyncio.run(_exercise_latest_failed_selection())
