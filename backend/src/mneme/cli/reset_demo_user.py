"""Reset only demo-user state while preserving the shared paper catalog."""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass

from sqlalchemy import delete

from mneme.core.config import Settings, get_settings
from mneme.db.session import Database
from mneme.models.base import utc_now
from mneme.models.digest import Digest
from mneme.models.qa import QaConversation
from mneme.models.user import User, UserEvent, UserPreference

MISSING_USER_ERROR = "demo_user_id_not_configured"
UNKNOWN_USER_ERROR = "demo_user_not_found"


class DemoResetConfigurationError(RuntimeError):
    """The local demo identity is missing or has not been bootstrapped."""


@dataclass(frozen=True, slots=True)
class DemoResetResult:
    """Counts for user-owned records removed by one reset."""

    deleted_digests: int
    deleted_events: int
    deleted_qa_conversations: int


async def run(settings: Settings) -> DemoResetResult:
    """Restore seed-onboarding state without deleting shared papers or artifacts."""
    user_id = settings.demo_user_id
    if user_id is None:
        raise DemoResetConfigurationError(MISSING_USER_ERROR)

    database = Database.from_settings(settings)
    try:
        async with database.session_factory() as session:
            if await session.get(User, user_id) is None:
                raise DemoResetConfigurationError(UNKNOWN_USER_ERROR)

            event_result = await session.execute(
                delete(UserEvent).where(UserEvent.user_id == user_id)
            )
            qa_result = await session.execute(
                delete(QaConversation).where(QaConversation.user_id == user_id)
            )
            digest_result = await session.execute(delete(Digest).where(Digest.user_id == user_id))
            preference = await session.get(UserPreference, user_id)
            if preference is None:
                preference = UserPreference(user_id=user_id)
                session.add(preference)

            preference.explicit_topics = []
            preference.followed_authors = []
            preference.behavior_embedding = None
            preference.negative_behavior_embedding = None
            preference.behavior_embedding_model = None
            preference.behavior_confidence = 0.0
            preference.behavior_evidence = {}
            preference.model_version = 1
            preference.updated_at = utc_now()
            await session.commit()

            return DemoResetResult(
                deleted_digests=affected_row_count(digest_result),
                deleted_events=affected_row_count(event_result),
                deleted_qa_conversations=affected_row_count(qa_result),
            )
    finally:
        await database.dispose()


def affected_row_count(result: object) -> int:
    """Normalize driver-specific unknown row counts."""
    value = getattr(result, "rowcount", None)
    return value if value is not None and value >= 0 else 0


def main() -> None:
    """Reset the configured demo user and emit safe machine-readable counts."""
    try:
        result = asyncio.run(run(get_settings()))
    except DemoResetConfigurationError as error:
        print(
            json.dumps({"error": str(error), "status": "error"}, sort_keys=True),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    except Exception:
        print(
            json.dumps({"error": "demo_reset_unavailable", "status": "error"}, sort_keys=True),
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    print(
        json.dumps(
            {
                "deleted_digests": result.deleted_digests,
                "deleted_events": result.deleted_events,
                "deleted_qa_conversations": result.deleted_qa_conversations,
                "status": "ok",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
