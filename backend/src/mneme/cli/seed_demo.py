"""Prepare or resume installation-local production demo state."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Never

from mneme.core.config import get_settings
from mneme.demo.manifest import (
    DemoManifestError,
    load_default_demo_seed_manifest,
    load_demo_seed_manifest,
)
from mneme.demo.seeding import seed_demo
from mneme.demo.seeding_support import (
    DemoSeedConfig,
    DemoSeedConfigurationError,
    DemoSeedError,
    read_private_demo_token,
)

CONFIG_ERROR = "demo_seed_configuration_invalid"
SEED_ERROR = "demo_seed_failed"


class JsonArgumentParser(argparse.ArgumentParser):
    """Return stable JSON for invalid orchestration arguments."""

    def error(self, message: str) -> Never:
        del message
        _print_error(CONFIG_ERROR, "Demo seed arguments are invalid.")
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded demo-seed parser."""
    parser = JsonArgumentParser(
        description="Prepare an installation-local replayable Mneme demo account."
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token-file", type=Path, default=Path("/etc/mneme/demo.token"))
    parser.add_argument("--lock-file", type=Path, default=Path("/var/lib/mneme/demo-seed.lock"))
    parser.add_argument("--request-timeout-seconds", type=float, default=900)
    parser.add_argument("--ready-timeout-seconds", type=float, default=900)
    parser.add_argument("--poll-interval-seconds", type=float, default=2)
    return parser


def _print_error(code: str, message: str) -> None:
    print(
        json.dumps({"error": code, "message": message, "status": "error"}, sort_keys=True),
        file=sys.stderr,
    )


def main() -> None:
    """Validate a plan offline or execute it against the local production API."""
    arguments = build_parser().parse_args()
    try:
        manifest = (
            load_demo_seed_manifest(arguments.manifest)
            if arguments.manifest is not None
            else load_default_demo_seed_manifest()
        )
        if arguments.dry_run:
            print(
                json.dumps(
                    {
                        "event_count": len(manifest.events),
                        "manifest_id": manifest.manifest_id,
                        "manifest_sha256": manifest.content_sha256(),
                        "paper_count": manifest.onboarding_limit,
                        "schema_version": "demo-seed-plan-v1",
                        "stages": ["bootstrap", "onboarding", "ready", "preferences", "events"],
                        "status": "dry_run",
                    },
                    sort_keys=True,
                )
            )
            return
        config = DemoSeedConfig(
            base_url=arguments.base_url,
            lock_file=arguments.lock_file,
            request_timeout_seconds=arguments.request_timeout_seconds,
            ready_timeout_seconds=arguments.ready_timeout_seconds,
            poll_interval_seconds=arguments.poll_interval_seconds,
        )
        settings = get_settings()
        token = read_private_demo_token(arguments.token_file, settings)
        result = asyncio.run(seed_demo(settings, manifest, config, token=token))
    except (DemoManifestError, DemoSeedConfigurationError, ValueError):
        _print_error(CONFIG_ERROR, "Demo seed configuration is invalid.")
        raise SystemExit(2) from None
    except (DemoSeedError, OSError):
        _print_error(SEED_ERROR, "Demo seed operation did not complete.")
        raise SystemExit(1) from None
    print(json.dumps(result.as_dict(), sort_keys=True))


if __name__ == "__main__":
    main()
