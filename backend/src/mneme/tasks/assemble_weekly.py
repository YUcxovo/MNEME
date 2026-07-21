"""Cron-friendly CLI for idempotent weekly Research Briefing scheduling."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, date, datetime, timedelta

from arq import create_pool

from mneme.core.config import Settings, get_settings
from mneme.db.session import Database
from mneme.redis.arq import create_arq_redis_settings
from mneme.tasks.weekly_scheduler import (
    WeeklyScheduleError,
    WeeklyScheduleSummary,
    schedule_weekly,
    validate_week_start,
)


def _parse_date(value: str) -> date:
    try:
        return validate_week_start(date.fromisoformat(value))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "week start must be a Monday in YYYY-MM-DD format"
        ) from error


def current_week_start(today: date) -> date:
    """Return the UTC calendar week's canonical Monday."""
    return today - timedelta(days=today.weekday())


def build_parser() -> argparse.ArgumentParser:
    """Build the zero-argument cron command with an optional backfill period."""
    parser = argparse.ArgumentParser(
        description="Schedule the demo user's weekly Research Briefing."
    )
    parser.add_argument(
        "--week-start",
        type=_parse_date,
        help="UTC Monday for an explicit weekly backfill (YYYY-MM-DD)",
    )
    return parser


async def run(
    *,
    settings: Settings | None = None,
    week_start: date | None = None,
) -> WeeklyScheduleSummary:
    """Schedule the demo user/week and release database/Redis resources."""
    resolved_settings = settings or get_settings()
    user_id = resolved_settings.demo_user_id
    if user_id is None:
        raise ValueError("MNEME_DEMO_USER_ID is required for weekly briefings.")
    resolved_week = validate_week_start(week_start or current_week_start(datetime.now(UTC).date()))

    database = Database(resolved_settings.database_url, echo=resolved_settings.debug)
    queue = None
    try:
        queue = await create_pool(
            create_arq_redis_settings(resolved_settings),
            default_queue_name=resolved_settings.arq_queue_name,
        )
        async with database.session_factory() as session:
            return await schedule_weekly(
                session,
                queue,
                user_id=user_id,
                week_start=resolved_week,
            )
    finally:
        if queue is not None:
            await queue.aclose()
        await database.dispose()


def main() -> None:
    """Schedule weekly work, emit JSON, and return a cron-safe exit status."""
    arguments = build_parser().parse_args()
    try:
        summary = asyncio.run(run(week_start=arguments.week_start))
    except (WeeklyScheduleError, ValueError) as error:
        payload: dict[str, object] = {"error": "weekly_schedule_failed", "message": str(error)}
        if isinstance(error, WeeklyScheduleError):
            payload["job_id"] = str(error.job_id)
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)
        raise SystemExit(1) from None
    except Exception:
        print(
            json.dumps(
                {
                    "error": "weekly_schedule_unavailable",
                    "message": "Weekly briefing scheduling failed unexpectedly.",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    print(
        json.dumps(
            {
                "job_created": summary.job_created,
                "job_dispatched": summary.job_dispatched,
                "job_id": str(summary.job_id),
                "job_requeued": summary.job_requeued,
                "job_unchanged": summary.job_unchanged,
                "user_id": str(summary.user_id),
                "week_start": summary.week_start.isoformat(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
