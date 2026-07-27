"""Replay stored events into the active behavior profile for one user."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from uuid import UUID

from mneme.core.config import Settings, get_settings
from mneme.db.session import Database
from mneme.services.behavior_v2 import BehaviorProfile
from mneme.services.events import BehaviorEventService, EventUserNotFoundError

MISSING_USER_ERROR = "behavior_user_id_not_configured"
UNKNOWN_USER_ERROR = "behavior_user_not_found"


class BehaviorReplayConfigurationError(RuntimeError):
    """Required non-secret replay configuration is absent."""


def build_parser() -> argparse.ArgumentParser:
    """Build the standalone behavior-profile replay parser."""
    parser = argparse.ArgumentParser(
        description="Recompute one behavior profile from authoritative raw events."
    )
    parser.add_argument(
        "--user-id",
        type=UUID,
        help="user UUID; defaults to MNEME_DEMO_USER_ID",
    )
    return parser


def resolve_user_id(settings: Settings, requested: UUID | None) -> UUID:
    """Resolve an explicit or configured user without touching infrastructure."""
    user_id = requested or settings.demo_user_id
    if user_id is None:
        raise BehaviorReplayConfigurationError(MISSING_USER_ERROR)
    return user_id


async def run(settings: Settings, *, user_id: UUID) -> BehaviorProfile:
    """Recompute one profile and guarantee database resource cleanup."""
    database = Database(settings.database_url, echo=settings.debug)
    try:
        async with database.session_factory() as session:
            service = BehaviorEventService(
                session,
                embedding_model=settings.ai_embedding_model,
            )
            return await service.recompute(user_id)
    finally:
        await database.dispose()


def _success_payload(
    *,
    user_id: UUID,
    embedding_model: str,
    profile: BehaviorProfile,
) -> dict[str, object]:
    return {
        "behavior_confidence": profile.confidence,
        "embedding_model": embedding_model,
        "evidence": profile.evidence.as_json(),
        "has_negative_profile": profile.negative_embedding is not None,
        "has_positive_profile": profile.positive_embedding is not None,
        "model_name": profile.model_name,
        "model_version": profile.model_version,
        "status": "ok",
        "user_id": str(user_id),
    }


def main() -> None:
    """Replay one profile and emit only safe machine-readable metadata."""
    arguments = build_parser().parse_args()
    settings = get_settings()
    try:
        user_id = resolve_user_id(settings, arguments.user_id)
        profile = asyncio.run(run(settings, user_id=user_id))
    except BehaviorReplayConfigurationError:
        print(json.dumps({"error": MISSING_USER_ERROR, "status": "error"}), file=sys.stderr)
        raise SystemExit(2) from None
    except EventUserNotFoundError:
        print(json.dumps({"error": UNKNOWN_USER_ERROR, "status": "error"}), file=sys.stderr)
        raise SystemExit(2) from None
    except Exception:
        print(
            json.dumps(
                {
                    "error": "behavior_replay_unavailable",
                    "message": "Behavior profile replay failed unexpectedly.",
                    "status": "error",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    print(
        json.dumps(
            _success_payload(
                user_id=user_id,
                embedding_model=settings.ai_embedding_model,
                profile=profile,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
