"""PostgreSQL proof of the durable summary-dispatch API loop."""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from pipeline_e2e_support import RecordingQueue
from sqlalchemy import delete, select

from mneme.api.dependencies.ai import get_task_queue
from mneme.core.config import Environment, Settings
from mneme.core.security import token_sha256
from mneme.db.session import Database
from mneme.main import create_app
from mneme.models.job import JobStatus, PipelineJob, PipelineStage
from mneme.models.paper import Paper, PaperVersion, ProcessingStatus
from mneme.models.user import User
from mneme.repositories.job_identity import download_idempotency_key

DATABASE_URL = os.getenv("MNEME_DATABASE_URL", "")
BACKEND_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 30, 8, 30, tzinfo=UTC)

pytestmark = [pytest.mark.db, pytest.mark.pipeline, pytest.mark.api]

if not DATABASE_URL:
    pytest.skip(
        "MNEME_DATABASE_URL is not configured for PostgreSQL integration tests",
        allow_module_level=True,
    )


@pytest.fixture(scope="module", autouse=True)
def upgrade_database() -> None:
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")


async def _seed(database: Database) -> tuple[UUID, UUID, UUID, str, int]:
    suffix = uuid4().hex[:12]
    user_id = uuid4()
    paper_id = uuid4()
    version_id = uuid4()
    arxiv_id = f"summary.{suffix}"
    version_number = 1
    async with database.session_factory() as session, session.begin():
        session.add(User(id=user_id, display_name=f"Summary Dispatch User {suffix}"))
        session.add(
            Paper(
                id=paper_id,
                arxiv_id=arxiv_id,
                title="A Durable Summary Dispatch",
                abstract="A deterministic paper for the summary dispatch integration test.",
                primary_category="cs.SE",
                categories=["cs.SE"],
                pdf_url=f"https://arxiv.org/pdf/{arxiv_id}v1",
                processing_status=ProcessingStatus.METADATA_ONLY,
                published_at=NOW,
                source_updated_at=NOW,
            )
        )
        await session.flush()
        session.add(
            PaperVersion(
                id=version_id,
                paper_id=paper_id,
                version_number=version_number,
                submitted_at=NOW,
            )
        )
    return user_id, paper_id, version_id, arxiv_id, version_number


async def _cleanup(database: Database, *, user_id: UUID, paper_id: UUID) -> None:
    async with database.session_factory() as session, session.begin():
        await session.execute(delete(User).where(User.id == user_id))
        await session.execute(delete(Paper).where(Paper.id == paper_id))


async def _exercise() -> None:
    database = Database(DATABASE_URL)
    user_id, paper_id, version_id, arxiv_id, version_number = await _seed(database)
    token = f"summary-dispatch-token-{uuid4().hex}"
    queue = RecordingQueue()
    application = create_app(
        Settings(
            environment=Environment.TESTING,
            database_url=DATABASE_URL,
            demo_user_id=user_id,
            demo_token_sha256=token_sha256(token),
            _env_file=None,
        )
    )

    async def queue_override() -> RecordingQueue:
        return queue

    application.dependency_overrides[get_task_queue] = queue_override
    headers = {"Authorization": f"Bearer {token}"}
    try:
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.get(f"/v1/papers/{paper_id}/summary", headers=headers)
            assert first.status_code == 202
            first_payload = first.json()
            job_id = UUID(first_payload["id"])
            assert first_payload["stage"] == PipelineStage.DOWNLOAD_PDF.value
            assert first_payload["status"] == JobStatus.QUEUED.value

            polled = await client.get(f"/v1/jobs/{job_id}", headers=headers)
            repeated = await client.get(f"/v1/papers/{paper_id}/summary", headers=headers)

        assert polled.status_code == 200
        assert polled.json()["id"] == str(job_id)
        assert polled.json()["stage"] == PipelineStage.DOWNLOAD_PDF.value
        assert polled.json()["status"] == JobStatus.QUEUED.value
        assert repeated.status_code == 202
        assert repeated.json()["id"] == str(job_id)

        assert len(queue.calls) == 1
        function, args, kwargs = queue.calls[0]
        assert function == PipelineStage.DOWNLOAD_PDF.value
        assert args == (str(paper_id), str(version_id))
        assert kwargs == {
            "job_id": str(job_id),
            "_job_id": f"pipeline:{job_id}:attempt:1",
        }

        async with database.session_factory() as session:
            paper = await session.get(Paper, paper_id)
            jobs = list(
                (
                    await session.scalars(
                        select(PipelineJob).where(PipelineJob.paper_id == paper_id)
                    )
                ).all()
            )

        assert paper is not None and paper.processing_status is ProcessingStatus.QUEUED
        assert len(jobs) == 1
        job = jobs[0]
        assert job.id == job_id
        assert job.paper_version_id == version_id
        assert job.idempotency_key == download_idempotency_key(
            paper_id=paper_id,
            paper_version_id=version_id,
            arxiv_id=arxiv_id,
            version_number=version_number,
        )
        assert job.stage is PipelineStage.DOWNLOAD_PDF
        assert job.status is JobStatus.QUEUED
        assert job.attempt_count == 0
        assert job.dispatched_at is not None
    finally:
        await _cleanup(database, user_id=user_id, paper_id=paper_id)
        await application.state.redis.aclose()
        await application.state.database.dispose()
        await database.dispose()


def test_summary_api_persists_and_dispatches_one_reusable_job() -> None:
    asyncio.run(_exercise())
