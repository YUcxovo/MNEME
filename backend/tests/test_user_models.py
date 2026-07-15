"""Metadata tests for the v0.1 user domain."""

import pytest
from pgvector.sqlalchemy import Vector
from sqlalchemy import Enum

from mneme.models import EMBEDDING_DIMENSIONS, Base, UserEventType


@pytest.mark.base
@pytest.mark.db
def test_user_tables_are_registered() -> None:
    assert {"users", "user_preferences", "user_events"} <= set(Base.metadata.tables)


@pytest.mark.base
@pytest.mark.db
def test_behavior_embedding_contract() -> None:
    table = Base.metadata.tables["user_preferences"]
    vector_type = table.c.behavior_embedding.type

    assert isinstance(vector_type, Vector)
    assert vector_type.dim == EMBEDDING_DIMENSIONS
    assert table.c.behavior_embedding.nullable
    assert table.c.behavior_embedding_model.nullable
    assert any(
        constraint.name == "ck_user_preferences_behavior_embedding_has_model"
        for constraint in table.constraints
    )


@pytest.mark.base
@pytest.mark.db
def test_event_id_and_optional_paper_contract() -> None:
    table = Base.metadata.tables["user_events"]
    event_enum = table.c.event_type.type

    assert table.c.id.primary_key
    assert table.c.paper_id.nullable
    assert isinstance(event_enum, Enum)
    assert set(event_enum.enums) == {event.value for event in UserEventType}
    assert any(index.name == "ix_user_events_user_occurred" for index in table.indexes)
