"""Generate a fresh weekly briefing for a local end-to-end demo."""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import exists, select

from mneme.core.config import Settings, get_settings
from mneme.db.session import Database
from mneme.models.base import utc_now
from mneme.models.digest import Digest, DigestType
from mneme.models.user import UserPreference
from mneme.repositories.digests import DigestRepository
from mneme.services.recommendation import RecommendedDigestService

SEED_GENERATOR_VERSION = "seed-onboarding-v1"
MISSING_USER_ERROR = "demo_user_id_not_configured"
SEED_REQUIRED_ERROR = "seed_onboarding_required"


class DemoWeeklyConfigurationError(RuntimeError):
    """The configured local demo cannot generate a meaningful weekly briefing."""


@dataclass(frozen=True, slots=True)
class DemoWeeklyResult:
    """Safe metadata used by the local Android notification trigger."""

    digest_id: UUID
    entry_count: int
    maximum_relevance: float | None


async def run(settings: Settings) -> DemoWeeklyResult:
    """Generate with the production recommender after real seed onboarding."""
    user_id = settings.demo_user_id
    if user_id is None:
        raise DemoWeeklyConfigurationError(MISSING_USER_ERROR)

    database = Database.from_settings(settings)
    try:
        async with database.session_factory() as session:
            preference = await session.get(UserPreference, user_id)
            if preference is None or not preference.explicit_topics:
                raise DemoWeeklyConfigurationError(SEED_REQUIRED_ERROR)

            seed_completed = await session.scalar(
                select(
                    exists().where(
                        Digest.user_id == user_id,
                        Digest.generator_version == SEED_GENERATOR_VERSION,
                    )
                )
            )
            if not seed_completed:
                raise DemoWeeklyConfigurationError(SEED_REQUIRED_ERROR)

            service = RecommendedDigestService(
                DigestRepository(session),
                candidate_days=settings.ai_recommendation_candidate_days,
                max_entries=settings.ai_recommendation_max_entries,
            )
            bundle = await service.generate(
                user_id,
                digest_type=DigestType.WEEKLY,
                as_of=utc_now(),
            )
            await session.commit()

            scores = [float(entry.relevance_score) for entry in bundle.entries]
            return DemoWeeklyResult(
                digest_id=bundle.digest.id,
                entry_count=len(bundle.entries),
                maximum_relevance=max(scores, default=None),
            )
    finally:
        await database.dispose()


def main() -> None:
    """Generate one briefing and emit only safe machine-readable metadata."""
    try:
        result = asyncio.run(run(get_settings()))
    except DemoWeeklyConfigurationError as error:
        print(
            json.dumps({"error": str(error), "status": "error"}, sort_keys=True),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    except Exception:
        print(
            json.dumps(
                {
                    "error": "demo_weekly_generation_unavailable",
                    "status": "error",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    print(
        json.dumps(
            {
                "digest_id": str(result.digest_id),
                "entry_count": result.entry_count,
                "maximum_relevance": result.maximum_relevance,
                "status": "ok",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
