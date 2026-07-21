"""PostgreSQL proof of the M2 arXiv-to-briefing skeletal pipeline."""

import asyncio
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from pipeline_e2e_support import (
    FixtureDownloader,
    FixtureEmbedder,
    FixtureParser,
    FixtureSummarizer,
    RecordingQueue,
)
from sqlalchemy import delete, func, select

from mneme.core.config import Environment, Settings
from mneme.core.security import token_sha256
from mneme.db.session import Database
from mneme.main import create_app
from mneme.models.artifact import PaperChunk, PaperSummary
from mneme.models.digest import Digest, DigestEntry, DigestType
from mneme.models.job import JobStatus, PipelineJob, PipelineStage
from mneme.models.paper import Paper, PaperVersion, ProcessingStatus
from mneme.models.user import User, UserPreference
from mneme.repositories.job_identity import download_idempotency_key
from mneme.repositories.jobs import PipelineJobRepository
from mneme.services.documents import DocumentStorage
from mneme.tasks.ai_jobs import chunk_paper, embed_chunks, summarize_paper
from mneme.tasks.digest_jobs import assemble_digest
from mneme.tasks.document_jobs import download_pdf, parse_pdf
from mneme.tasks.weekly_scheduler import schedule_weekly

DATABASE_URL = os.getenv("MNEME_DATABASE_URL", "")
BACKEND_ROOT = Path(__file__).resolve().parents[1]
WEEK_START = date(2026, 7, 20)

pytestmark = [pytest.mark.db, pytest.mark.pipeline, pytest.mark.api, pytest.mark.rag]

if not DATABASE_URL:
    pytest.skip(
        "MNEME_DATABASE_URL is not configured for PostgreSQL integration tests",
        allow_module_level=True,
    )


@pytest.fixture(scope="module", autouse=True)
def upgrade_database() -> None:
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")


async def _seed(database: Database) -> tuple[UUID, UUID, UUID, UUID]:
    suffix = uuid4().hex[:12]
    user_id = uuid4()
    paper_id = uuid4()
    version_id = uuid4()
    async with database.session_factory() as session:
        session.add(User(id=user_id, display_name=f"Pipeline User {suffix}"))
        session.add(
            UserPreference(
                user_id=user_id,
                explicit_topics=["pipeline"],
                followed_authors=[],
                model_version=1,
            )
        )
        session.add(
            Paper(
                id=paper_id,
                arxiv_id=f"e2e.{suffix}",
                title="A Revision-Safe Research Pipeline",
                abstract="A deterministic paper about a staged research pipeline.",
                primary_category="cs.AI",
                categories=["cs.AI"],
                pdf_url=f"https://arxiv.org/pdf/e2e.{suffix}v1",
                processing_status=ProcessingStatus.METADATA_ONLY,
                published_at=datetime(2026, 7, 19, tzinfo=UTC),
                source_updated_at=datetime(2026, 7, 19, tzinfo=UTC),
            )
        )
        session.add(
            PaperVersion(
                id=version_id,
                paper_id=paper_id,
                version_number=1,
                submitted_at=datetime(2026, 7, 19, tzinfo=UTC),
            )
        )
        await session.flush()
        job, _ = await PipelineJobRepository(session).get_or_create(
            idempotency_key=download_idempotency_key(
                paper_id=paper_id,
                paper_version_id=version_id,
                arxiv_id=f"e2e.{suffix}",
                version_number=1,
            ),
            stage=PipelineStage.DOWNLOAD_PDF,
            paper_id=paper_id,
            paper_version_id=version_id,
        )
        await session.commit()
        return user_id, paper_id, version_id, job.id


async def _run_queued(
    queue: RecordingQueue,
    function: str,
    handler: Any,
    context: dict[str, Any],
) -> str:
    args, kwargs = queue.pop(function)
    return await handler(context, *args, job_id=cast(str, kwargs["job_id"]))


async def _assert_api(*, database_url: str, user_id: UUID, token: str, job_id: UUID) -> None:
    application = create_app(
        Settings(
            environment=Environment.TESTING,
            database_url=database_url,
            demo_user_id=user_id,
            demo_token_sha256=token_sha256(token),
            _env_file=None,
        )
    )
    try:
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {token}"}
            job_response = await client.get(f"/v1/jobs/{job_id}", headers=headers)
            digest_response = await client.get("/v1/digests", headers=headers)

        assert job_response.status_code == 200
        assert job_response.json()["status"] == "succeeded"
        assert job_response.json()["stage"] == "assemble_digest"
        assert digest_response.status_code == 200
        payload = digest_response.json()
        assert payload["items"][0]["digest_type"] == "weekly"
        assert payload["items"][0]["entries"][0]["paper"]["title"] == (
            "A Revision-Safe Research Pipeline"
        )
    finally:
        await application.state.redis.aclose()
        await application.state.database.dispose()


async def _exercise(tmp_path: Path) -> None:
    database = Database(DATABASE_URL)
    user_id, paper_id, version_id, download_job_id = await _seed(database)
    queue = RecordingQueue()
    settings = Settings(database_url=DATABASE_URL, demo_user_id=user_id, _env_file=None)
    context: dict[str, Any] = {
        "database": database,
        "document_storage": DocumentStorage(tmp_path),
        "pdf_downloader": FixtureDownloader(),
        "pdf_parser": FixtureParser(),
        "summarizer": FixtureSummarizer(),
        "embedder": FixtureEmbedder(),
        "redis": queue,
        "settings": settings,
    }
    try:
        assert (
            await download_pdf(context, str(paper_id), str(version_id), job_id=str(download_job_id))
            == "ok"
        )
        assert await _run_queued(queue, "parse_pdf", parse_pdf, context) == "ok"
        assert await _run_queued(queue, "summarize_paper", summarize_paper, context) == "ok"
        assert await _run_queued(queue, "chunk_paper", chunk_paper, context) == "ok"
        assert await _run_queued(queue, "embed_chunks", embed_chunks, context) == "ok"

        async with database.session_factory() as session:
            weekly = await schedule_weekly(
                session,
                queue,
                user_id=user_id,
                week_start=WEEK_START,
            )
        assert await _run_queued(queue, "assemble_digest", assemble_digest, context) == "ok"

        async with database.session_factory() as session:
            paper = await session.get(Paper, paper_id)
            jobs = list(
                (await session.scalars(select(PipelineJob).where(PipelineJob.paper_id == paper_id)))
                .unique()
                .all()
            )
            summaries = await session.scalar(
                select(func.count(PaperSummary.id)).where(PaperSummary.paper_id == paper_id)
            )
            chunks = await session.scalar(
                select(func.count(PaperChunk.id)).where(PaperChunk.paper_id == paper_id)
            )
            embedded = await session.scalar(
                select(func.count(PaperChunk.embedding)).where(PaperChunk.paper_id == paper_id)
            )
            digest = await session.scalar(
                select(Digest).where(
                    Digest.user_id == user_id,
                    Digest.digest_type == DigestType.WEEKLY,
                )
            )
            if digest is None:
                raise AssertionError("weekly digest was not persisted")
            entries = await session.scalar(
                select(func.count(DigestEntry.paper_id)).where(DigestEntry.digest_id == digest.id)
            )

        assert paper is not None and paper.processing_status is ProcessingStatus.READY
        assert {job.stage for job in jobs} == {
            PipelineStage.DOWNLOAD_PDF,
            PipelineStage.PARSE_PDF,
            PipelineStage.SUMMARIZE_PAPER,
            PipelineStage.CHUNK_PAPER,
            PipelineStage.EMBED_CHUNKS,
        }
        assert all(job.status is JobStatus.SUCCEEDED for job in jobs)
        assert summaries == 1
        assert chunks is not None and chunks > 0 and chunks == embedded
        assert entries == 1
        await _assert_api(
            database_url=DATABASE_URL,
            user_id=user_id,
            token=f"pipeline-token-{uuid4().hex}",
            job_id=weekly.job_id,
        )
    finally:
        async with database.session_factory() as session:
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
            await session.execute(delete(Paper).where(Paper.id == paper_id))
            await session.commit()
        await database.dispose()


def test_m2_pipeline_reaches_weekly_briefing_api(tmp_path: Path) -> None:
    asyncio.run(_exercise(tmp_path))
