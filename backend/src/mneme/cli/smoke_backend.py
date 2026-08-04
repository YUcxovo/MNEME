"""Run the public-API deployed MVP acceptance sequence."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Never
from uuid import UUID

from mneme.demo.smoke import run_mvp_smoke
from mneme.demo.smoke_types import (
    MvpSmokeConfig,
    MvpSmokeConfigurationError,
    read_private_smoke_token,
    validate_smoke_token,
)

CONFIG_ERROR = "mvp_smoke_configuration_invalid"


class JsonArgumentParser(argparse.ArgumentParser):
    """Return stable JSON for invalid smoke-test arguments."""

    def error(self, message: str) -> Never:
        del message
        _print_config_error()
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded deployment smoke-test parser."""
    parser = JsonArgumentParser(description="Exercise the deployed Mneme MVP over HTTP.")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("MNEME_MVP_SMOKE_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--seed",
        default=os.environ.get("MNEME_MVP_SMOKE_SEED", "1706.03762"),
    )
    parser.add_argument("--paper-id", type=UUID, default=os.environ.get("MNEME_MVP_SMOKE_PAPER_ID"))
    parser.add_argument("--question", default=os.environ.get("MNEME_MVP_SMOKE_QUESTION"))
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--request-timeout-seconds", type=float, default=120)
    parser.add_argument("--deadline-seconds", type=float, default=600)
    parser.add_argument("--poll-interval-seconds", type=float, default=1)
    parser.add_argument("--maximum-summary-jobs", type=int, default=8)
    parser.add_argument("--maximum-catalog-pages", type=int, default=5)
    parser.add_argument("--minimum-graph-nodes", type=int, default=2)
    parser.add_argument("--minimum-graph-edges", type=int, default=1)
    return parser


def _print_config_error() -> None:
    print(
        json.dumps(
            {
                "error": CONFIG_ERROR,
                "message": "MVP smoke configuration is invalid.",
                "status": "error",
            },
            sort_keys=True,
        ),
        file=sys.stderr,
    )


def _resolve_token(token_file: Path | None) -> str:
    if token_file is not None:
        return read_private_smoke_token(token_file)
    token = os.environ.get("MNEME_MVP_SMOKE_TOKEN")
    if token is None:
        raise MvpSmokeConfigurationError("Smoke token is not configured")
    return validate_smoke_token(token)


def main() -> None:
    """Print a sanitized report and use 0/1/2 for pass/fail/configuration."""
    arguments = build_parser().parse_args()
    try:
        config = MvpSmokeConfig(
            base_url=arguments.base_url,
            seed_arxiv_id=arguments.seed,
            seed_paper_id=arguments.paper_id,
            question=arguments.question,
            request_timeout_seconds=arguments.request_timeout_seconds,
            deadline_seconds=arguments.deadline_seconds,
            poll_interval_seconds=arguments.poll_interval_seconds,
            maximum_summary_jobs=arguments.maximum_summary_jobs,
            maximum_catalog_pages=arguments.maximum_catalog_pages,
            minimum_graph_nodes=arguments.minimum_graph_nodes,
            minimum_graph_edges=arguments.minimum_graph_edges,
        )
        token = _resolve_token(arguments.token_file)
        report = asyncio.run(run_mvp_smoke(config, token=token))
    except (MvpSmokeConfigurationError, ValueError):
        _print_config_error()
        raise SystemExit(2) from None
    print(json.dumps(report.as_dict(), sort_keys=True))
    if report.status != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
