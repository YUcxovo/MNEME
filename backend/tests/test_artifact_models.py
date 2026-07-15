"""Metadata tests for revision-aware paper artifacts."""

import pytest
from pgvector.sqlalchemy import Vector
from sqlalchemy import Enum, Numeric
from sqlalchemy.orm import configure_mappers

from mneme.models import EMBEDDING_DIMENSIONS, Base, SourceMatchStatus, SummaryStatus


@pytest.mark.base
@pytest.mark.db
def test_artifact_tables_are_registered_and_mapped() -> None:
    configure_mappers()

    assert {"paper_chunks", "paper_summaries"} <= set(Base.metadata.tables)


@pytest.mark.base
@pytest.mark.db
def test_chunks_are_revision_scoped() -> None:
    table = Base.metadata.tables["paper_chunks"]

    assert isinstance(table.c.embedding.type, Vector)
    assert table.c.embedding.type.dim == EMBEDDING_DIMENSIONS
    assert "uq_paper_chunks_version_index" in {constraint.name for constraint in table.constraints}
    assert "fk_paper_chunks_version_paper" in {constraint.name for constraint in table.constraints}
    assert not any(
        constraint.name == "uq_paper_chunks_content_hash" for constraint in table.constraints
    )


@pytest.mark.base
@pytest.mark.db
def test_summaries_preserve_generation_provenance() -> None:
    table = Base.metadata.tables["paper_summaries"]
    status_type = table.c.status.type
    source_match_type = table.c.source_match_status.type
    cost_type = table.c.estimated_cost.type

    assert isinstance(status_type, Enum)
    assert set(status_type.enums) == {status.value for status in SummaryStatus}
    assert isinstance(source_match_type, Enum)
    assert set(source_match_type.enums) == {status.value for status in SourceMatchStatus}
    assert isinstance(cost_type, Numeric)
    assert cost_type.precision == 12
    assert cost_type.scale == 6
    assert "uq_paper_summaries_generation" in {constraint.name for constraint in table.constraints}
