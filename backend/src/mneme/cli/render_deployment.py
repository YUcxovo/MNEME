"""Render production deployment templates into an operator staging directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Never

from mneme.ops.deployment import (
    DeploymentRenderConfig,
    DeploymentRenderError,
    render_deployment,
)

INPUT_ERROR = "deployment_render_input_invalid"
RENDER_ERROR = "deployment_render_failed"


class JsonArgumentParser(argparse.ArgumentParser):
    """Return a stable machine-readable argument error."""

    def error(self, message: str) -> Never:
        del message
        _print_error(INPUT_ERROR, "Deployment render arguments are invalid.")
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    """Build the non-privileged deployment renderer parser."""
    parser = JsonArgumentParser(description="Render Mneme deployment files into staging.")
    parser.add_argument("--server-name", required=True)
    parser.add_argument("--template-dir", type=Path, default=Path("deploy/templates"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--install-dir", type=Path, default=Path("/opt/mneme"))
    parser.add_argument("--environment-file", type=Path, default=Path("/etc/mneme/backend.env"))
    parser.add_argument("--paper-data-dir", type=Path, default=Path("/var/lib/mneme/papers"))
    parser.add_argument("--service-user", default="mneme")
    parser.add_argument("--service-group", default="mneme")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--api-workers", type=int, default=2)
    return parser


def _print_error(code: str, message: str) -> None:
    print(
        json.dumps({"error": code, "message": message, "status": "error"}, sort_keys=True),
        file=sys.stderr,
    )


def main() -> None:
    """Render deterministic files and print their names as sorted JSON."""
    arguments = build_parser().parse_args()
    try:
        config = DeploymentRenderConfig(
            server_name=arguments.server_name,
            install_dir=arguments.install_dir,
            environment_file=arguments.environment_file,
            paper_data_dir=arguments.paper_data_dir,
            service_user=arguments.service_user,
            service_group=arguments.service_group,
            api_port=arguments.api_port,
            api_workers=arguments.api_workers,
        )
        rendered = render_deployment(arguments.template_dir, arguments.output_dir, config)
    except (DeploymentRenderError, OSError):
        _print_error(RENDER_ERROR, "Deployment files could not be rendered safely.")
        raise SystemExit(1) from None
    print(
        json.dumps(
            {
                "files": sorted(path.name for path in rendered),
                "schema_version": "deployment-render-v1",
                "status": "ok",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
