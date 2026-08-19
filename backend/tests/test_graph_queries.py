"""Tests for deterministic bounded citation graph traversal."""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from mneme.models.paper import Paper
from mneme.repositories.graph_queries import SqlGraphRepository


def _paper(paper_id: UUID, title: str) -> Paper:
    return Paper(
        id=paper_id,
        arxiv_id=paper_id.hex,
        title=title,
        abstract="Abstract",
        primary_category="cs.AI",
        categories=["cs.AI"],
        pdf_url=f"https://arxiv.org/pdf/{paper_id.hex}",
    )


def _rows(values: list[tuple[object, ...]]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = values
    return result


def _scalars(values: list[Paper]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = values
    return result


@pytest.mark.base
@pytest.mark.db
def test_depth_two_traversal_is_bidirectional_bounded_and_induced() -> None:
    async def exercise() -> tuple[object, AsyncMock]:
        center_id, first_id, second_id, truncated_id = (uuid4() for _ in range(4))
        center = _paper(center_id, "Center")
        first = _paper(first_id, "First")
        second = _paper(second_id, "Second")
        session = AsyncMock(spec=AsyncSession)
        session.get.return_value = center
        session.execute.side_effect = [
            _rows([(first_id, center_id)]),
            _rows([(first_id, second_id), (truncated_id, first_id)]),
            _rows([(first_id, center_id, None), (first_id, second_id, 0.7)]),
        ]
        session.scalars.side_effect = [_scalars([first]), _scalars([second])]

        snapshot = await SqlGraphRepository(cast(AsyncSession, session)).get_ego_graph(
            center_id, depth=2, max_nodes=3
        )
        assert snapshot is not None
        assert list(snapshot.nodes) == [center_id, first_id, second_id]
        assert [(edge.source, edge.target) for edge in snapshot.edges] == [
            (first_id, center_id),
            (first_id, second_id),
        ]
        assert snapshot.edges[1].weight == 0.7
        return snapshot, session

    _, session = asyncio.run(exercise())
    expansion = cast(Select, session.execute.await_args_list[0].args[0])
    expansion_sql = str(expansion.compile(dialect=postgresql.dialect()))
    assert "citations.source_paper_id IS NOT NULL" in expansion_sql
    assert "citations.target_paper_id IS NOT NULL" in expansion_sql
    assert " OR " in expansion_sql
    paper_query = cast(Select, session.scalars.await_args_list[0].args[0])
    assert "ORDER BY papers.published_at DESC, papers.id" in str(
        paper_query.compile(dialect=postgresql.dialect())
    )


@pytest.mark.base
@pytest.mark.db
def test_center_is_always_returned_and_limit_one_reads_no_edges() -> None:
    async def exercise() -> tuple[object, AsyncMock]:
        center = _paper(uuid4(), "Center")
        session = AsyncMock(spec=AsyncSession)
        session.get.return_value = center
        snapshot = await SqlGraphRepository(cast(AsyncSession, session)).get_ego_graph(
            center.id, depth=1, max_nodes=1
        )
        assert snapshot is not None
        assert tuple(snapshot.nodes) == (center.id,)
        assert snapshot.edges == ()
        return snapshot, session

    _, session = asyncio.run(exercise())
    session.execute.assert_not_awaited()
    session.scalars.assert_not_awaited()


@pytest.mark.base
@pytest.mark.db
def test_missing_center_and_invalid_bounds_are_explicit() -> None:
    async def missing() -> None:
        session = AsyncMock(spec=AsyncSession)
        session.get.return_value = None
        result = await SqlGraphRepository(cast(AsyncSession, session)).get_ego_graph(
            uuid4(), depth=1, max_nodes=50
        )
        assert result is None

    asyncio.run(missing())

    repository = SqlGraphRepository(cast(AsyncSession, AsyncMock(spec=AsyncSession)))
    with pytest.raises(ValueError, match="depth"):
        asyncio.run(repository.get_ego_graph(uuid4(), depth=3, max_nodes=50))
    with pytest.raises(ValueError, match="max_nodes"):
        asyncio.run(repository.get_ego_graph(uuid4(), depth=1, max_nodes=201))
