"""Metadata tests for single-paper Q&A persistence."""

import pytest
from sqlalchemy import Enum, Numeric
from sqlalchemy.orm import configure_mappers

from mneme.models import Base, QaRole, QaSourceMatchStatus


@pytest.mark.base
@pytest.mark.db
def test_qa_tables_are_registered_and_mapped() -> None:
    configure_mappers()

    assert {"qa_conversations", "qa_messages"} <= set(Base.metadata.tables)


@pytest.mark.base
@pytest.mark.db
def test_qa_messages_are_ordered_and_source_labeled() -> None:
    table = Base.metadata.tables["qa_messages"]
    role_type = table.c.role.type
    source_type = table.c.source_match_status.type

    assert isinstance(role_type, Enum)
    assert set(role_type.enums) == {role.value for role in QaRole}
    assert isinstance(source_type, Enum)
    assert set(source_type.enums) == {status.value for status in QaSourceMatchStatus}
    assert "uq_qa_messages_conversation_sequence" in {
        constraint.name for constraint in table.constraints
    }


@pytest.mark.base
@pytest.mark.db
def test_qa_messages_retain_generation_telemetry() -> None:
    table = Base.metadata.tables["qa_messages"]
    cost_type = table.c.estimated_cost.type

    assert isinstance(cost_type, Numeric)
    assert cost_type.precision == 12
    assert cost_type.scale == 6
    assert table.c.provider.nullable
    assert table.c.input_tokens.nullable
    assert table.c.latency_ms.nullable
