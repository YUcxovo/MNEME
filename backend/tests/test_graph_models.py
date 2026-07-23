"""Metadata tests for citation graph persistence."""

import pytest

from mneme.models import Base


@pytest.mark.base
@pytest.mark.db
def test_citation_endpoint_and_deduplication_contract() -> None:
    table = Base.metadata.tables["citations"]
    constraint_names = {constraint.name for constraint in table.constraints}
    index_names = {index.name for index in table.indexes}

    assert table.c.source_paper_id.nullable
    assert table.c.external_source_id.nullable
    assert table.c.target_paper_id.nullable
    assert table.c.external_target_id.nullable
    assert {
        "ck_citations_one_source",
        "ck_citations_one_target",
        "ck_citations_has_local_endpoint",
        "ck_citations_no_self_edge",
    } <= constraint_names
    assert {
        "uq_citations_internal_edge",
        "uq_citations_external_target_edge",
        "uq_citations_external_source_edge",
        "ix_citations_external_target_id",
        "ix_citations_target_paper_id",
    } <= index_names
    assert all(
        index.unique
        for index in table.indexes
        if index.name is not None and index.name.startswith("uq_")
    )
