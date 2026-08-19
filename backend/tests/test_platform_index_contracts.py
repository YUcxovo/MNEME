"""Schema contracts for bounded platform query access paths."""

from typing import cast

import pytest
from sqlalchemy import Index, Table

from mneme.models.digest import Digest
from mneme.models.graph import Citation
from mneme.models.job import PipelineJob
from mneme.models.paper import Paper

pytestmark = [pytest.mark.base, pytest.mark.db]


def _index(table: object, name: str) -> Index:
    resolved = cast(Table, table)
    return next(index for index in resolved.indexes if index.name == name)


def _columns(index: Index) -> tuple[str, ...]:
    return tuple(column.name for column in index.columns)


def test_keyset_pagination_indexes_match_repository_ordering() -> None:
    assert _columns(_index(Paper.__table__, "ix_papers_published_id")) == (
        "published_at",
        "id",
    )
    assert _columns(_index(Paper.__table__, "ix_papers_category_published")) == (
        "primary_category",
        "published_at",
        "id",
    )
    assert _columns(_index(Digest.__table__, "ix_digests_user_generated")) == (
        "user_id",
        "generated_at",
        "id",
    )


def test_dispatch_and_graph_indexes_match_bounded_queries() -> None:
    assert _columns(_index(PipelineJob.__table__, "ix_pipeline_jobs_dispatchable")) == (
        "status",
        "dispatched_at",
        "created_at",
    )
    internal_edges = _index(Citation.__table__, "uq_citations_internal_edge")
    assert _columns(internal_edges) == ("source_paper_id", "target_paper_id")
    assert internal_edges.dialect_options["postgresql"]["where"] is not None
    assert _columns(_index(Citation.__table__, "ix_citations_target_paper_id")) == (
        "target_paper_id",
    )
