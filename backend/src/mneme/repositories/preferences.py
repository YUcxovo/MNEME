"""User-preference persistence with idempotent full replacement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.user import User, UserPreference


@dataclass(frozen=True, slots=True)
class PreferenceSnapshot:
    """Transport-neutral representation of stored explicit preferences."""

    topics: list[str]
    followed_authors: list[str]
    model_version: int
    updated_at: datetime

    @classmethod
    def from_model(cls, preference: UserPreference) -> PreferenceSnapshot:
        """Copy mutable JSON arrays out of an ORM preference row."""
        return cls(
            topics=list(preference.explicit_topics),
            followed_authors=list(preference.followed_authors),
            model_version=preference.model_version,
            updated_at=preference.updated_at,
        )


class PreferenceRepository:
    """Read and replace preferences for the pre-provisioned demo user."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_preferences(self, user_id: UUID) -> PreferenceSnapshot | None:
        """Return current preferences, or `None` when the user is not bootstrapped."""
        preference = await self._session.get(UserPreference, user_id)
        if preference is None:
            return None
        return PreferenceSnapshot.from_model(preference)

    async def replace_preferences(
        self,
        user_id: UUID,
        *,
        topics: list[str],
        followed_authors: list[str],
    ) -> PreferenceSnapshot | None:
        """Atomically replace both lists without updating an identical row."""
        async with self._session.begin():
            user_exists = await self._session.scalar(
                select(User.id).where(User.id == user_id).with_for_update()
            )
            if user_exists is None:
                return None
            preference = await self._session.scalar(
                select(UserPreference).where(UserPreference.user_id == user_id).with_for_update()
            )
            if preference is None:
                preference = UserPreference(
                    user_id=user_id,
                    explicit_topics=list(topics),
                    followed_authors=list(followed_authors),
                )
                self._session.add(preference)
                await self._session.flush()
            elif (
                preference.explicit_topics != topics
                or preference.followed_authors != followed_authors
            ):
                preference.explicit_topics = list(topics)
                preference.followed_authors = list(followed_authors)
                await self._session.flush()
            snapshot = PreferenceSnapshot.from_model(preference)

        return snapshot
