"""Cron-friendly CLI for daily arXiv metadata scheduling."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, date, datetime

from arq import create_pool

from mneme.core.config import Settings, get_settings
from mneme.db.session import Database
from mneme.redis.arq import create_arq_redis_settings
from mneme.tasks.daily_scheduler import (
    DailyScheduleError,
    DailyScheduleSummary,
    schedule_daily,
    validate_request,
)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from error


def build_parser() -> argparse.ArgumentParser:
    """Build the zero-argument cron command with optional backfill controls."""
    parser = argparse.ArgumentParser(
        description="Schedule idempotent daily arXiv metadata ingestion jobs."
    )
    parser.add_argument(
        "--category",
        action="append",
        dest="categories",
        help="arXiv category; repeat for multiple categories (defaults to configuration)",
    )
    parser.add_argument(
        "--date",
        type=_parse_date,
        dest="run_date",
        help="UTC schedule date for an explicit backfill (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        help="bounded results fetched for each category",
    )
    return parser


async def run(
    *,
    settings: Settings | None = None,
    run_date: date | None = None,
    categories: tuple[str, ...] | None = None,
    max_results: int | None = None,
) -> DailyScheduleSummary:
    """Schedule the configured UTC day and release database/Redis resources."""
    resolved_settings = settings or get_settings()
    resolved_date = run_date or datetime.now(UTC).date()
    resolved_max_results = (
        max_results if max_results is not None else resolved_settings.arxiv_daily_max_results
    )
    resolved_categories = validate_request(
        resolved_settings,
        categories=(
            categories if categories is not None else resolved_settings.daily_arxiv_categories
        ),
        max_results=resolved_max_results,
    )

    database = Database.from_settings(resolved_settings)
    queue = None
    try:
        queue = await create_pool(
            create_arq_redis_settings(resolved_settings),
            default_queue_name=resolved_settings.arq_queue_name,
        )
        async with database.session_factory() as session:
            return await schedule_daily(
                session,
                queue,
                run_date=resolved_date,
                categories=resolved_categories,
                max_results=resolved_max_results,
            )
    finally:
        if queue is not None:
            await queue.aclose()
        await database.dispose()


def main() -> None:
    """Schedule daily work, emit JSON, and return a cron-safe exit status."""
    arguments = build_parser().parse_args()
    try:
        summary = asyncio.run(
            run(
                run_date=arguments.run_date,
                categories=tuple(arguments.categories) if arguments.categories else None,
                max_results=arguments.max_results,
            )
        )
    except (DailyScheduleError, ValueError) as error:
        payload: dict[str, object] = {"error": "daily_schedule_failed", "message": str(error)}
        if isinstance(error, DailyScheduleError):
            payload["failed_categories"] = error.failed_categories
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)
        raise SystemExit(1) from None
    except Exception:
        print(
            json.dumps(
                {
                    "error": "daily_schedule_unavailable",
                    "message": "Daily metadata scheduling failed unexpectedly.",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    print(
        json.dumps(
            {
                "categories": summary.categories,
                "jobs_created": summary.jobs_created,
                "jobs_dispatched": summary.jobs_dispatched,
                "jobs_requeued": summary.jobs_requeued,
                "jobs_unchanged": summary.jobs_unchanged,
                "run_date": summary.run_date.isoformat(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
