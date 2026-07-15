"""Metadata tests for immutable research briefings."""

import pytest
from sqlalchemy import Enum
from sqlalchemy.orm import configure_mappers

from mneme.models import Base, DigestType


@pytest.mark.base
@pytest.mark.db
def test_digest_tables_are_registered_and_mapped() -> None:
    configure_mappers()

    assert {"digests", "digest_entries"} <= set(Base.metadata.tables)


@pytest.mark.base
@pytest.mark.db
def test_digest_snapshot_has_reproducibility_fields() -> None:
    table = Base.metadata.tables["digests"]
    digest_type = table.c.digest_type.type

    assert isinstance(digest_type, Enum)
    assert set(digest_type.enums) == {item.value for item in DigestType}
    assert not table.c.preference_model_version.nullable
    assert not table.c.generator_version.nullable
    assert "ix_digests_user_generated" in {index.name for index in table.indexes}


@pytest.mark.base
@pytest.mark.db
def test_digest_entries_preserve_rank_and_score() -> None:
    table = Base.metadata.tables["digest_entries"]

    assert {column.name for column in table.primary_key.columns} == {"digest_id", "paper_id"}
    assert "uq_digest_entries_digest_rank" in {constraint.name for constraint in table.constraints}
    assert "ck_digest_entries_score_range" in {constraint.name for constraint in table.constraints}
