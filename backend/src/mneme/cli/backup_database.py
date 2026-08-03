"""Create one validated local PostgreSQL backup."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Never

from mneme.ops.backup import (
    BackupConfig,
    BackupConfigurationError,
    BackupError,
    run_database_backup,
    validate_libpq_environment,
)

CONFIG_ERROR = "database_backup_configuration_invalid"
BACKUP_ERROR = "database_backup_failed"


class JsonArgumentParser(argparse.ArgumentParser):
    """Return stable JSON for invalid arguments."""

    def error(self, message: str) -> Never:
        del message
        _print_error(CONFIG_ERROR, "Database backup arguments are invalid.")
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded local-backup parser."""
    parser = JsonArgumentParser(description="Create a validated Mneme database backup.")
    parser.add_argument("--output-dir", type=Path, default=Path("/var/backups/mneme"))
    parser.add_argument("--retention-count", type=int, default=7)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--lock-wait-timeout-seconds", type=int, default=10)
    return parser


def _print_error(code: str, message: str) -> None:
    print(
        json.dumps({"error": code, "message": message, "status": "error"}, sort_keys=True),
        file=sys.stderr,
    )


def main() -> None:
    """Run one backup and print only its non-sensitive manifest."""
    arguments = build_parser().parse_args()
    try:
        validate_libpq_environment(os.environ)
        config = BackupConfig(
            output_dir=arguments.output_dir,
            retention_count=arguments.retention_count,
            timeout_seconds=arguments.timeout_seconds,
            lock_wait_timeout_seconds=arguments.lock_wait_timeout_seconds,
        )
        manifest = run_database_backup(config)
    except BackupConfigurationError:
        _print_error(CONFIG_ERROR, "Database backup configuration is invalid.")
        raise SystemExit(2) from None
    except (BackupError, OSError):
        _print_error(BACKUP_ERROR, "Database backup could not be completed safely.")
        raise SystemExit(1) from None
    payload = manifest.as_dict()
    payload["status"] = "ok"
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
