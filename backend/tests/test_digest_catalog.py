"""Unit tests for authenticated digest keyset pagination."""

import asyncio
import base64
import json
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.digest import Digest, DigestType
from mneme.repositories.digests import (
    DigestRepository,
    InvalidDigestCursorError,
    decode_digest_cursor,
    encode_digest_cursor,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000111")


def _digest(*, generated_at: datetime, digest_id: UUID | None = None) -> Digest:
    return Digest(
        id=digest_id or uuid4(),
        user_id=USER_ID,
        digest_type=DigestType.WEEKLY,
        generated_at=generated_at,
        preference_model_version=1,
        generator_version="test-v1",
    )


@pytest.mark.base
@pytest.mark.api
def test_digest_cursor_round_trip_normalizes_utc() -> None:
    digest_id = uuid4()
    timestamp = datetime.fromisoformat("2026-07-21T17:30:00+08:00")

    encoded = encode_digest_cursor(timestamp, digest_id)
    decoded = decode_digest_cursor(encoded)

    assert decoded.digest_id == digest_id
    assert decoded.generated_at == timestamp.astimezone(UTC)
    assert "=" not in encoded


@pytest.mark.base
@pytest.mark.api
@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "not-base64!",
        "e30",
        "eyJ2IjoyLCJnZW5lcmF0ZWRfYXQiOiIyMDI2LTA3LTIxVDAwOjAwOjAwWiIsImlkIjoiYmFkIn0",
        "5Lit5paH",
    ],
)
def test_invalid_digest_cursor_is_rejected(cursor: str) -> None:
    with pytest.raises(InvalidDigestCursorError, match="invalid digest cursor"):
        decode_digest_cursor(cursor)


@pytest.mark.base
@pytest.mark.api
def test_boolean_digest_cursor_version_is_rejected() -> None:
    raw = json.dumps(
        {
            "v": True,
            "generated_at": "2026-07-21T00:00:00Z",
            "id": str(uuid4()),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    cursor = base64.urlsafe_b64encode(raw).decode().rstrip("=")

    with pytest.raises(InvalidDigestCursorError, match="invalid digest cursor"):
        decode_digest_cursor(cursor)


@pytest.mark.base
@pytest.mark.api
def test_digest_query_is_user_scoped_and_builds_lookahead_cursor() -> None:
    timestamp = datetime(2026, 7, 21, tzinfo=UTC)
    digests = [
        _digest(generated_at=timestamp, digest_id=UUID(int=3)),
        _digest(generated_at=timestamp, digest_id=UUID(int=2)),
        _digest(generated_at=timestamp, digest_id=UUID(int=1)),
    ]
    scalar_result = Mock()
    scalar_result.all.return_value = digests
    session = Mock(spec=AsyncSession)
    session.scalars = AsyncMock(return_value=scalar_result)
    repository = DigestRepository(cast(AsyncSession, session))

    page = asyncio.run(repository.list_digests(user_id=USER_ID, limit=2))

    assert page.items == digests[:2]
    assert page.next_cursor is not None
    assert decode_digest_cursor(page.next_cursor).digest_id == digests[1].id
    await_args = session.scalars.await_args
    assert await_args is not None
    statement = await_args.args[0]
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert f"digests.user_id = '{USER_ID}'" in sql
    assert "ORDER BY digests.generated_at DESC, digests.id DESC" in sql
    assert "LIMIT 3" in sql


@pytest.mark.base
@pytest.mark.api
def test_digest_query_applies_timestamp_and_id_cursor() -> None:
    timestamp = datetime(2026, 7, 21, tzinfo=UTC)
    scalar_result = Mock()
    scalar_result.all.return_value = []
    session = Mock(spec=AsyncSession)
    session.scalars = AsyncMock(return_value=scalar_result)
    repository = DigestRepository(cast(AsyncSession, session))

    page = asyncio.run(
        repository.list_digests(
            user_id=USER_ID,
            limit=20,
            cursor=decode_digest_cursor(encode_digest_cursor(timestamp, UUID(int=10))),
        )
    )

    assert page.items == []
    assert page.next_cursor is None
    await_args = session.scalars.await_args
    assert await_args is not None
    statement = await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "digests.user_id =" in sql
    assert "digests.generated_at <" in sql
    assert "digests.id <" in sql
