"""Run host-private production health checks."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Never

from mneme.core.config import get_settings
from mneme.ops.health import run_platform_health
from mneme.ops.health_types import PlatformHealthConfig, PlatformHealthConfigurationError

CONFIG_ERROR = "platform_health_configuration_invalid"


class JsonArgumentParser(argparse.ArgumentParser):
    """Return stable JSON for invalid health-check arguments."""

    def error(self, message: str) -> Never:
        del message
        _print_config_error()
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded health-check parser."""
    parser = JsonArgumentParser(description="Check private Mneme platform health.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--backup-dir", type=Path, default=Path("/var/backups/mneme"))
    parser.add_argument("--minimum-disk-percent", type=int, default=10)
    parser.add_argument("--minimum-memory-percent", type=int, default=10)
    parser.add_argument("--maximum-backup-age-hours", type=int, default=30)
    parser.add_argument("--maximum-ingestion-age-hours", type=int, default=36)
    parser.add_argument("--maximum-digest-age-hours", type=int, default=192)
    parser.add_argument("--maximum-failed-jobs", type=int, default=0)
    parser.add_argument("--probe-timeout-seconds", type=float, default=5.0)
    return parser


def _print_config_error() -> None:
    print(
        json.dumps(
            {
                "error": CONFIG_ERROR,
                "message": "Platform health configuration is invalid.",
                "status": "error",
            },
            sort_keys=True,
        ),
        file=sys.stderr,
    )


def main() -> None:
    """Print one aggregate report and use stable operational exit codes."""
    arguments = build_parser().parse_args()
    try:
        config = PlatformHealthConfig(
            base_url=arguments.base_url,
            backup_dir=arguments.backup_dir,
            minimum_disk_available_percent=arguments.minimum_disk_percent,
            minimum_memory_available_percent=arguments.minimum_memory_percent,
            maximum_backup_age_hours=arguments.maximum_backup_age_hours,
            maximum_ingestion_age_hours=arguments.maximum_ingestion_age_hours,
            maximum_digest_age_hours=arguments.maximum_digest_age_hours,
            maximum_failed_jobs=arguments.maximum_failed_jobs,
            probe_timeout_seconds=arguments.probe_timeout_seconds,
        )
        report = asyncio.run(run_platform_health(get_settings(), config))
    except (PlatformHealthConfigurationError, ValueError):
        _print_config_error()
        raise SystemExit(2) from None
    print(json.dumps(report.as_dict(), sort_keys=True))
    if report.status != "healthy":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
