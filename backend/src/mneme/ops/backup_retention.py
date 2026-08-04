"""Conservative retention for validated Mneme database archives."""

import json
import os
import re
from pathlib import Path

_ARCHIVE_PATTERN = re.compile(r"^mneme-\d{8}T\d{12}Z\.dump$")


def apply_retention(output_dir: Path, retention_count: int) -> None:
    """Delete only old archive/manifest pairs produced by the current schema."""
    valid_pairs: list[tuple[Path, Path]] = []
    for manifest_path in output_dir.glob("mneme-*.json"):
        if manifest_path.is_symlink() or not manifest_path.is_file():
            continue
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            archive_name = payload["archive"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
        expected_archive = manifest_path.with_suffix(".dump")
        archive_path = output_dir / str(archive_name)
        if (
            payload.get("schema_version") != "mneme-backup-v1"
            or archive_path != expected_archive
            or not _ARCHIVE_PATTERN.fullmatch(archive_path.name)
            or archive_path.is_symlink()
            or not archive_path.is_file()
        ):
            continue
        valid_pairs.append((manifest_path, archive_path))

    for manifest_path, archive_path in sorted(valid_pairs)[:-retention_count]:
        archive_path.unlink()
        manifest_path.unlink()
    _fsync_directory(output_dir)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
