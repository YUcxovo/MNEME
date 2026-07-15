"""Unit tests for preference normalization and idempotent persistence."""

import asyncio
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.api.schemas.preferences import PreferenceUpdate
from mneme.models.user import UserPreference
from mneme.repositories.preferences import PreferenceRepository


@pytest.mark.base
@pytest.mark.api
def test_preference_update_normalizes_and_stably_deduplicates() -> None:
    update = PreferenceUpdate(
        topics=["  Machine Learning ", "machine learning", "STRASSE", "Straße"],
        followed_authors=[" Alice Smith ", "ALICE SMITH", "Bob Jones"],
    )

    assert update.topics == ["machine learning", "strasse"]
    assert update.followed_authors == ["alice smith", "bob jones"]


@pytest.mark.base
@pytest.mark.api
@pytest.mark.parametrize("empty_value", ["", " ", "\t\n"])
def test_preference_update_rejects_empty_normalized_entries(empty_value: str) -> None:
    with pytest.raises(ValidationError):
        PreferenceUpdate(topics=[empty_value], followed_authors=[])


@pytest.mark.base
@pytest.mark.api
def test_preference_update_requires_both_lists_and_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PreferenceUpdate.model_validate({"topics": []})
    with pytest.raises(ValidationError):
        PreferenceUpdate.model_validate({"topics": [], "followed_authors": [], "unknown": "value"})


@pytest.mark.base
@pytest.mark.api
def test_preference_raw_item_limit_is_checked_before_deduplication() -> None:
    with pytest.raises(ValidationError):
        PreferenceUpdate(topics=["duplicate"] * 101, followed_authors=[])


def _session_with_transaction() -> Mock:
    transaction = AsyncMock()
    session = Mock(spec=AsyncSession)
    session.begin.return_value = transaction
    session.scalar = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.mark.base
@pytest.mark.db
def test_identical_preference_replacement_does_not_flush_or_touch_timestamp() -> None:
    user_id = uuid4()
    updated_at = datetime(2026, 7, 15, tzinfo=UTC)
    stored = UserPreference(
        user_id=user_id,
        explicit_topics=["ai"],
        followed_authors=["ada lovelace"],
        model_version=3,
        updated_at=updated_at,
    )
    session = _session_with_transaction()
    session.scalar.return_value = stored
    repository = PreferenceRepository(cast(AsyncSession, session))

    snapshot = asyncio.run(
        repository.replace_preferences(
            user_id,
            topics=["ai"],
            followed_authors=["ada lovelace"],
        )
    )

    assert snapshot is not None
    assert snapshot.updated_at is updated_at
    session.flush.assert_not_awaited()


@pytest.mark.base
@pytest.mark.db
def test_changed_preference_replacement_flushes_both_lists() -> None:
    user_id = uuid4()
    stored = UserPreference(
        user_id=user_id,
        explicit_topics=["ai"],
        followed_authors=[],
        model_version=1,
        updated_at=datetime(2026, 7, 15, tzinfo=UTC),
    )
    session = _session_with_transaction()
    session.scalar.return_value = stored
    repository = PreferenceRepository(cast(AsyncSession, session))

    snapshot = asyncio.run(
        repository.replace_preferences(
            user_id,
            topics=["systems"],
            followed_authors=["grace hopper"],
        )
    )

    assert snapshot is not None
    assert snapshot.topics == ["systems"]
    assert snapshot.followed_authors == ["grace hopper"]
    session.flush.assert_awaited_once()


@pytest.mark.base
@pytest.mark.db
def test_preference_replacement_reports_unbootstrapped_user() -> None:
    session = _session_with_transaction()
    session.scalar.side_effect = [None, None]
    repository = PreferenceRepository(cast(AsyncSession, session))

    snapshot = asyncio.run(
        repository.replace_preferences(
            uuid4(),
            topics=[],
            followed_authors=[],
        )
    )

    assert snapshot is None
    session.add.assert_not_called()
    session.flush.assert_not_awaited()
