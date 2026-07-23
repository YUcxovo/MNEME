"""Metadata tests for papers, revisions, and ordered authorship."""

import pytest
from sqlalchemy import ARRAY, Enum
from sqlalchemy.orm import configure_mappers

from mneme.models import Base, ParseQuality, ProcessingStatus


@pytest.mark.base
@pytest.mark.db
def test_paper_catalog_tables_are_registered() -> None:
    configure_mappers()

    assert {"papers", "paper_versions", "authors", "paper_authors"} <= set(Base.metadata.tables)


@pytest.mark.base
@pytest.mark.db
def test_paper_snapshot_supports_keyset_and_categories() -> None:
    table = Base.metadata.tables["papers"]
    status_type = table.c.processing_status.type

    assert not table.c.published_at.nullable
    assert not table.c.source_updated_at.nullable
    assert table.c.semantic_scholar_id.nullable
    assert isinstance(table.c.categories.type, ARRAY)
    assert isinstance(status_type, Enum)
    assert set(status_type.enums) == {status.value for status in ProcessingStatus}
    assert {index.name for index in table.indexes} >= {
        "ix_papers_published_id",
        "ix_papers_category_published",
    }


@pytest.mark.base
@pytest.mark.db
def test_revision_and_authorship_constraints() -> None:
    versions = Base.metadata.tables["paper_versions"]
    authorship = Base.metadata.tables["paper_authors"]
    parse_quality_type = versions.c.parse_quality.type

    assert versions.c.source_checksum.nullable
    assert versions.c.source_size_bytes.nullable
    assert versions.c.downloaded_at.nullable
    assert versions.c.parsed_checksum.nullable
    assert versions.c.parser_version.nullable
    assert versions.c.parse_quality.nullable
    assert versions.c.parsed_at.nullable
    assert isinstance(parse_quality_type, Enum)
    assert set(parse_quality_type.enums) == {quality.value for quality in ParseQuality}
    assert versions.c.submitted_at.nullable
    assert "uq_paper_versions_paper_version" in {
        constraint.name for constraint in versions.constraints
    }
    assert "ck_paper_versions_parse_metadata_complete" in {
        constraint.name for constraint in versions.constraints
    }
    assert "ck_paper_versions_source_size_non_negative" in {
        constraint.name for constraint in versions.constraints
    }
    assert "ck_paper_versions_source_metadata_complete" in {
        constraint.name for constraint in versions.constraints
    }
    assert {column.name for column in authorship.primary_key.columns} == {
        "paper_id",
        "author_id",
    }
    assert "uq_paper_authors_paper_order" in {
        constraint.name for constraint in authorship.constraints
    }
