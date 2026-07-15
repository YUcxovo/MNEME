"""Metadata tests for citation graph persistence."""

import pytest

from mneme.models import Base


@pytest.mark.base
@pytest.mark.db
def test_citation_target_and_deduplication_contract() -> None:
    table = Base.metadata.tables["citations"]
    constraint_names = {constraint.name for constraint in table.constraints}
    index_names = {index.name for index in table.indexes}

    assert table.c.target_paper_id.nullable
    assert table.c.external_target_id.nullable
    assert "ck_citations_has_target" in constraint_names
    assert "ck_citations_no_self_edge" in constraint_names
    assert {"uq_citations_internal_edge", "uq_citations_external_edge"} <= index_names
    assert all(index.unique for index in table.indexes)
