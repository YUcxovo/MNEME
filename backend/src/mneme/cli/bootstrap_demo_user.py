"""Provision the configured demo user without handling its bearer token."""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict

from mneme.core.config import Settings, get_settings
from mneme.db.session import Database
from mneme.repositories.demo_user_bootstrap import (
    DemoUserBootstrapRepository,
    DemoUserBootstrapResult,
)

DEFAULT_DISPLAY_NAME = "Mneme Demo User"
MISSING_USER_ERROR = "demo_user_id_not_configured"


class DemoUserConfigurationError(RuntimeError):
    """Required non-secret demo-user configuration is absent."""


def build_parser() -> argparse.ArgumentParser:
    """Build the standalone bootstrap command parser."""
    parser = argparse.ArgumentParser(
        description="Create the configured demo user and its default preferences."
    )
    parser.add_argument(
        "--display-name",
        default=DEFAULT_DISPLAY_NAME,
        help="display name used only when the user is first created",
    )
    return parser


async def run(settings: Settings, *, display_name: str) -> DemoUserBootstrapResult:
    """Bootstrap configured rows while guaranteeing resource cleanup."""
    if settings.demo_user_id is None:
        raise DemoUserConfigurationError(MISSING_USER_ERROR)

    database = Database.from_settings(settings)
    try:
        async with database.session_factory() as session:
            repository = DemoUserBootstrapRepository(session)
            return await repository.bootstrap(
                settings.demo_user_id,
                display_name=display_name,
            )
    finally:
        await database.dispose()


def main() -> None:
    """Run the bootstrap and emit a stable JSON result."""
    arguments = build_parser().parse_args()
    try:
        result = asyncio.run(run(get_settings(), display_name=arguments.display_name))
    except DemoUserConfigurationError:
        print(json.dumps({"error": MISSING_USER_ERROR, "status": "error"}), file=sys.stderr)
        raise SystemExit(2) from None
    print(json.dumps({"status": "ok", **asdict(result)}, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
