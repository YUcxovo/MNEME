"""Run the production deployment preflight gate."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Never

from mneme.core.config import get_settings
from mneme.ops.preflight import run_preflight
from mneme.ops.preflight_probe import expected_migration_head

CONFIG_ERROR = "deployment_preflight_configuration_invalid"


class JsonArgumentParser(argparse.ArgumentParser):
    """Return stable JSON for invalid arguments."""

    def error(self, message: str) -> Never:
        del message
        _print_config_error()
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    """Build the deployment preflight parser."""
    parser = JsonArgumentParser(description="Validate a Mneme production deployment.")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run configuration checks only and record that live checks were skipped.",
    )
    parser.add_argument("--alembic-config", type=Path, default=Path("alembic.ini"))
    return parser


def _print_config_error() -> None:
    print(
        json.dumps(
            {
                "error": CONFIG_ERROR,
                "message": "Deployment preflight configuration is invalid.",
                "status": "error",
            },
            sort_keys=True,
        ),
        file=sys.stderr,
    )


def main() -> None:
    """Print one stable report and fail closed when any required check fails."""
    arguments = build_parser().parse_args()
    try:
        settings = get_settings()
        head = "offline" if arguments.offline else expected_migration_head(arguments.alembic_config)
        report = asyncio.run(run_preflight(settings, expected_head=head, offline=arguments.offline))
    except (OSError, ValueError):
        _print_config_error()
        raise SystemExit(2) from None
    print(json.dumps(report.as_dict(), sort_keys=True))
    if report.status != "ready":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
