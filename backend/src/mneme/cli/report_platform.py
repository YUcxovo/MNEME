"""Emit one bounded, non-sensitive platform operations snapshot."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, date, datetime
from typing import Never
from uuid import UUID

from mneme.core.config import Settings, get_settings
from mneme.db.session import Database
from mneme.repositories.operations import (
    MAX_DISPATCH_LEASE_SECONDS,
    MAX_FAILED_LIMIT,
    MAX_WINDOW_HOURS,
    PlatformOperationsRepository,
)

INPUT_ERROR = "platform_report_input_invalid"
UNAVAILABLE_ERROR = "platform_report_unavailable"


class PlatformReportInputError(ValueError):
    """One report bound is outside its supported range."""


class JsonArgumentParser(argparse.ArgumentParser):
    """Return stable JSON instead of argparse's free-form stderr output."""

    def error(self, message: str) -> Never:
        del message
        _print_error(INPUT_ERROR, "Platform report arguments are invalid.")
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded operations-report command parser."""
    parser = JsonArgumentParser(description="Report bounded Mneme platform operations state.")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--dispatch-lease-seconds", type=int, default=300)
    parser.add_argument("--failed-limit", type=int, default=20)
    return parser


def validate_bounds(
    *,
    window_hours: int,
    dispatch_lease_seconds: int,
    failed_limit: int,
) -> None:
    """Reject unbounded or nonsensical report requests before connecting."""
    if not 1 <= window_hours <= MAX_WINDOW_HOURS:
        raise PlatformReportInputError(f"window_hours must be between 1 and {MAX_WINDOW_HOURS}")
    if not 1 <= dispatch_lease_seconds <= MAX_DISPATCH_LEASE_SECONDS:
        raise PlatformReportInputError(
            f"dispatch_lease_seconds must be between 1 and {MAX_DISPATCH_LEASE_SECONDS}"
        )
    if not 0 <= failed_limit <= MAX_FAILED_LIMIT:
        raise PlatformReportInputError(f"failed_limit must be between 0 and {MAX_FAILED_LIMIT}")


async def run(
    settings: Settings,
    *,
    window_hours: int,
    dispatch_lease_seconds: int,
    failed_limit: int,
    now: datetime | None = None,
) -> dict[str, object]:
    """Read one snapshot and always release the database pool."""
    validate_bounds(
        window_hours=window_hours,
        dispatch_lease_seconds=dispatch_lease_seconds,
        failed_limit=failed_limit,
    )
    database = Database.from_settings(settings, echo=False)
    try:
        async with database.session_factory() as session:
            repository = PlatformOperationsRepository(session)
            return await repository.snapshot(
                now=now or datetime.now(UTC),
                window_hours=window_hours,
                dispatch_lease_seconds=dispatch_lease_seconds,
                failed_limit=failed_limit,
            )
    finally:
        await database.dispose()


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Unsupported report value type: {type(value).__name__}")


def _print_error(code: str, message: str) -> None:
    print(
        json.dumps({"error": code, "message": message, "status": "error"}, sort_keys=True),
        file=sys.stderr,
    )


def main() -> None:
    """Print one sorted JSON snapshot with stable safe failure contracts."""
    arguments = build_parser().parse_args()
    try:
        validate_bounds(
            window_hours=arguments.window_hours,
            dispatch_lease_seconds=arguments.dispatch_lease_seconds,
            failed_limit=arguments.failed_limit,
        )
        payload = asyncio.run(
            run(
                get_settings(),
                window_hours=arguments.window_hours,
                dispatch_lease_seconds=arguments.dispatch_lease_seconds,
                failed_limit=arguments.failed_limit,
            )
        )
    except PlatformReportInputError:
        _print_error(INPUT_ERROR, "Platform report arguments are outside supported bounds.")
        raise SystemExit(2) from None
    except Exception:
        _print_error(UNAVAILABLE_ERROR, "Platform operations data is temporarily unavailable.")
        raise SystemExit(1) from None

    print(json.dumps(payload, default=_json_default, sort_keys=True))


if __name__ == "__main__":
    main()
