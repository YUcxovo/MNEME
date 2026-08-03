"""Render non-secret production deployment artifacts into a staging directory."""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from string import Template

TEMPLATE_FILENAMES = (
    "backend.env.template",
    "mneme-api.service.template",
    "mneme-backup.service.template",
    "mneme-backup.timer.template",
    "mneme-bootstrap.service.template",
    "mneme-digest.service.template",
    "mneme-digest.timer.template",
    "mneme-health.service.template",
    "mneme-health.timer.template",
    "mneme-ingest.service.template",
    "mneme-ingest.timer.template",
    "mneme-migrate.service.template",
    "mneme-preflight.service.template",
    "mneme-seed.service.template",
    "mneme-smoke.service.template",
    "mneme-worker.service.template",
    "nginx-mneme-bootstrap.conf.template",
    "nginx-mneme-tls.conf.template",
)
_ACCOUNT_PATTERN = re.compile(r"^[a-z_][a-z0-9_-]{0,30}$")
_DNS_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_PATH_COMPONENT_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class DeploymentRenderError(ValueError):
    """A deployment manifest or template set is unsafe or incomplete."""


@dataclass(frozen=True)
class DeploymentRenderConfig:
    """Validated non-secret values used by the deployment templates."""

    server_name: str
    backup_dir: Path = Path("/var/backups/mneme")
    install_dir: Path = Path("/opt/mneme")
    environment_file: Path = Path("/etc/mneme/backend.env")
    paper_data_dir: Path = Path("/var/lib/mneme/papers")
    service_user: str = "mneme"
    service_group: str = "mneme"
    api_port: int = 8000
    api_workers: int = 2

    def __post_init__(self) -> None:
        _validate_fqdn(self.server_name)
        _validate_account(self.service_user, "service user")
        _validate_account(self.service_group, "service group")
        _validate_scoped_path(self.install_dir, Path("/opt"), "install directory")
        _validate_scoped_path(self.environment_file, Path("/etc"), "environment file")
        if self.environment_file.suffix != ".env":
            raise DeploymentRenderError("Environment file must use an .env suffix")
        _validate_scoped_path(self.paper_data_dir, Path("/var/lib"), "paper data directory")
        _validate_scoped_path(self.backup_dir, Path("/var/backups"), "backup directory")
        if not 1024 <= self.api_port <= 65535:
            raise DeploymentRenderError("API port must be between 1024 and 65535")
        if not 1 <= self.api_workers <= 8:
            raise DeploymentRenderError("API workers must be between 1 and 8")

    def as_mapping(self) -> dict[str, str]:
        """Return the complete string mapping accepted by all templates."""
        return {
            "api_host": "127.0.0.1",
            "api_port": str(self.api_port),
            "api_workers": str(self.api_workers),
            "backup_dir": str(self.backup_dir),
            "environment_file": str(self.environment_file),
            "install_dir": str(self.install_dir),
            "paper_data_dir": str(self.paper_data_dir),
            "server_name": self.server_name,
            "service_group": self.service_group,
            "service_user": self.service_user,
        }


def render_deployment(
    template_dir: Path,
    output_dir: Path,
    config: DeploymentRenderConfig,
) -> tuple[Path, ...]:
    """Render the exact template set atomically without installing host files."""
    expected = set(TEMPLATE_FILENAMES)
    actual = {path.name for path in template_dir.glob("*.template") if path.is_file()}
    if actual != expected:
        raise DeploymentRenderError("Deployment template set is incomplete or unexpected")
    if output_dir.is_symlink():
        raise DeploymentRenderError("Deployment output directory cannot be a symbolic link")
    output_dir.mkdir(parents=True, exist_ok=True)
    expected_outputs = {name.removesuffix(".template") for name in TEMPLATE_FILENAMES}
    if any(path.name not in expected_outputs for path in output_dir.iterdir()):
        raise DeploymentRenderError("Deployment output directory contains unexpected files")

    rendered_paths: list[Path] = []
    mapping = config.as_mapping()
    for filename in TEMPLATE_FILENAMES:
        source = template_dir / filename
        target = output_dir / filename.removesuffix(".template")
        if target.is_symlink():
            raise DeploymentRenderError("Deployment output cannot replace a symbolic link")
        try:
            rendered = Template(source.read_text(encoding="utf-8")).substitute(mapping)
        except (KeyError, ValueError) as exception:
            raise DeploymentRenderError(
                "Deployment template contains an invalid token"
            ) from exception
        _atomic_write(target, rendered, mode=0o600 if target.name == "backend.env" else 0o644)
        rendered_paths.append(target)
    return tuple(rendered_paths)


def _atomic_write(path: Path, content: str, *, mode: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.chmod(mode)
        temporary_path.replace(path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _validate_account(value: str, label: str) -> None:
    if not _ACCOUNT_PATTERN.fullmatch(value):
        raise DeploymentRenderError(f"Invalid {label}")


def _validate_fqdn(value: str) -> None:
    labels = value.split(".")
    if (
        len(value) > 253
        or len(labels) < 2
        or any(not _DNS_LABEL_PATTERN.fullmatch(x) for x in labels)
    ):
        raise DeploymentRenderError("Server name must be a valid fully qualified domain name")


def _validate_scoped_path(value: Path, parent: Path, label: str) -> None:
    if (
        not value.is_absolute()
        or ".." in value.parts
        or value == parent
        or not value.is_relative_to(parent)
        or any(not _PATH_COMPONENT_PATTERN.fullmatch(part) for part in value.parts[1:])
    ):
        raise DeploymentRenderError(f"Invalid {label}")
