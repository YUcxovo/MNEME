"""Idempotent persistence for the pre-provisioned demo user."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.base import utc_now
from mneme.models.user import User, UserPreference


@dataclass(frozen=True, slots=True)
class DemoUserBootstrapResult:
    """Outcome of one idempotent bootstrap transaction."""

    user_id: UUID
    user_created: bool
    preferences_created: bool


def normalize_display_name(value: str) -> str:
    """Normalize and validate the configured display name."""
    display_name = " ".join(value.split())
    if not display_name:
        raise ValueError("Demo user display name must not be empty")
    if len(display_name) > 200:
        raise ValueError("Demo user display name exceeds the database limit")
    return display_name


class DemoUserBootstrapRepository:
    """Create the configured user and its initial preferences exactly once."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bootstrap(self, user_id: UUID, *, display_name: str) -> DemoUserBootstrapResult:
        """Insert missing rows in one transaction without changing existing data."""
        normalized_display_name = normalize_display_name(display_name)
        now = utc_now()

        async with self._session.begin():
            user_statement = (
                postgresql_insert(User)
                .values(id=user_id, display_name=normalized_display_name, created_at=now)
                .on_conflict_do_nothing(constraint="pk_users")
                .returning(User.id)
            )
            user_result = await self._session.execute(user_statement)
            user_created = user_result.scalar_one_or_none() is not None

            preference_statement = (
                postgresql_insert(UserPreference)
                .values(
                    user_id=user_id,
                    explicit_topics=[],
                    followed_authors=[],
                    behavior_embedding=None,
                    behavior_embedding_model=None,
                    model_version=1,
                    updated_at=now,
                )
                .on_conflict_do_nothing(constraint="pk_user_preferences")
                .returning(UserPreference.user_id)
            )
            preference_result = await self._session.execute(preference_statement)
            preferences_created = preference_result.scalar_one_or_none() is not None

        return DemoUserBootstrapResult(
            user_id=user_id,
            user_created=user_created,
            preferences_created=preferences_created,
        )
