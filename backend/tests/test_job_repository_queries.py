"""Unit coverage for bounded pipeline-job selection queries."""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from mneme.repositories.jobs import PipelineJobRepository

PAPER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


@pytest.mark.base
@pytest.mark.db
@pytest.mark.pipeline
def test_failed_revision_query_is_limited_to_latest_paper_versions() -> None:
    async def exercise() -> Select:
        session = AsyncMock(spec=AsyncSession)
        rows = MagicMock()
        rows.all.return_value = []
        session.scalars.return_value = rows

        result = await PipelineJobRepository(
            cast(AsyncSession, session)
        ).list_failed_latest_revision_jobs((PAPER_ID,))

        assert result == []
        return cast(Select, session.scalars.await_args.args[0])

    statement = asyncio.run(exercise())
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "pipeline_jobs.status =" in sql
    assert "paper_versions.version_number = (SELECT max" in sql
    assert "paper_versions.paper_id = pipeline_jobs.paper_id" in sql
    assert "ORDER BY pipeline_jobs.created_at, pipeline_jobs.id" in sql


@pytest.mark.base
@pytest.mark.db
@pytest.mark.pipeline
def test_failed_revision_query_avoids_database_for_empty_scope() -> None:
    session = AsyncMock(spec=AsyncSession)

    result = asyncio.run(
        PipelineJobRepository(cast(AsyncSession, session)).list_failed_latest_revision_jobs(())
    )

    assert result == []
    session.scalars.assert_not_awaited()
