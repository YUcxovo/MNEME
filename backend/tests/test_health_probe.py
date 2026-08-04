"""Tests for concrete private host-health probes."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from mneme.core.config import Settings
from mneme.ops.health_probe import ProductionHealthProbe
from mneme.ops.health_types import PlatformHealthConfig

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


@pytest.mark.base
def test_health_probe_requires_exact_api_health_shapes(tmp_path: Path) -> None:
    async def responses(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(
            200,
            json={
                "status": "ready",
                "dependencies": {"postgresql": "ready", "redis": "ready"},
            },
        )

    client = httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(responses)
    )
    probe = ProductionHealthProbe(
        Settings(_env_file=None),
        PlatformHealthConfig(backup_dir=tmp_path),
        http_client=client,
    )

    assert asyncio.run(probe.api_liveness())
    assert asyncio.run(probe.api_readiness())
    asyncio.run(probe.aclose())


@pytest.mark.base
def test_health_probe_validates_latest_backup_pair(tmp_path: Path) -> None:
    archive = tmp_path / "mneme-20260803T100000000000Z.dump"
    archive.write_bytes(b"archive")
    (tmp_path / "latest.json").write_text(
        json.dumps(
            {
                "archive": archive.name,
                "completed_at": "2026-08-03T10:00:00Z",
                "schema_version": "mneme-backup-v1",
                "sha256": "a" * 64,
                "size_bytes": 7,
                "verification": "pg_restore_list",
            }
        ),
        encoding="utf-8",
    )
    client = httpx.AsyncClient(base_url="http://127.0.0.1:8000")
    probe = ProductionHealthProbe(
        Settings(_env_file=None),
        PlatformHealthConfig(backup_dir=tmp_path),
        http_client=client,
    )

    assert asyncio.run(probe.latest_backup()) == datetime(2026, 8, 3, 10, tzinfo=UTC)

    archive.write_bytes(b"wrong-size")
    with pytest.raises(ValueError):
        asyncio.run(probe.latest_backup())
    asyncio.run(probe.aclose())
