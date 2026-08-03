"""Live host-private probes for platform health."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import httpx
from redis.asyncio import Redis

from mneme.core.config import Settings
from mneme.db.session import Database
from mneme.models.job import PipelineStage
from mneme.ops.health_types import PlatformHealthConfig
from mneme.redis.client import create_redis_client
from mneme.repositories.operations import PlatformOperationsRepository

WORKER_HEALTH_KEY = "mneme:worker:health"


class ProductionHealthProbe:
    """Read platform state without exposing private observations."""

    def __init__(
        self,
        settings: Settings,
        config: PlatformHealthConfig,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._config = config
        self._database = Database.from_settings(settings, echo=False)
        self._redis: Redis = create_redis_client(settings)
        self._http = http_client or httpx.AsyncClient(
            base_url=config.base_url, timeout=httpx.Timeout(config.probe_timeout_seconds)
        )

    async def api_liveness(self) -> bool:
        response = await self._http.get("/v1/health")
        return response.status_code == 200 and response.json() == {"status": "ok"}

    async def api_readiness(self) -> bool:
        response = await self._http.get("/v1/health/ready")
        if response.status_code != 200:
            return False
        payload = response.json()
        dependencies = payload.get("dependencies", {}) if isinstance(payload, dict) else {}
        return payload.get("status") == "ready" and dependencies == {
            "postgresql": "ready",
            "redis": "ready",
        }

    async def worker_alive(self) -> bool:
        return bool(await self._redis.exists(WORKER_HEALTH_KEY))

    async def operations_snapshot(self, now: datetime) -> dict[str, object]:
        async with self._database.session_factory() as session:
            repository = PlatformOperationsRepository(session)
            return await repository.snapshot(
                now=now,
                window_hours=self._config.operations_window_hours,
                dispatch_lease_seconds=self._config.dispatch_lease_seconds,
                failed_limit=0,
            )

    async def pipeline_successes(self) -> dict[str, datetime | None]:
        stages = (PipelineStage.FETCH_METADATA, PipelineStage.ASSEMBLE_DIGEST)
        async with self._database.session_factory() as session:
            observed = await PlatformOperationsRepository(session).latest_success_by_stage(stages)
        return {stage.value: observed[stage] for stage in stages}

    async def paper_disk_space(self) -> tuple[int, int]:
        usage = shutil.disk_usage(self._settings.paper_storage_dir)
        return usage.total, usage.free

    async def backup_disk_space(self) -> tuple[int, int]:
        usage = shutil.disk_usage(self._config.backup_dir)
        return usage.total, usage.free

    async def memory_space(self) -> tuple[int, int]:
        values: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            key, raw_value = line.split(":", 1)
            if key in {"MemTotal", "MemAvailable"}:
                values[key] = int(raw_value.strip().split()[0]) * 1024
        return values["MemTotal"], values["MemAvailable"]

    async def latest_backup(self) -> datetime:
        latest_path = self._config.backup_dir / "latest.json"
        if latest_path.is_symlink() or not latest_path.is_file():
            raise ValueError("Latest backup manifest is unavailable")
        payload = json.loads(latest_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != "mneme-backup-v1":
            raise ValueError("Latest backup manifest is invalid")
        archive_name = payload.get("archive")
        if not isinstance(archive_name, str) or Path(archive_name).name != archive_name:
            raise ValueError("Latest backup archive identity is invalid")
        archive_path = self._config.backup_dir / archive_name
        if archive_path.is_symlink() or not archive_path.is_file():
            raise ValueError("Latest backup archive is unavailable")
        expected_size = payload.get("size_bytes")
        if (
            not isinstance(expected_size, int)
            or expected_size < 1
            or archive_path.stat().st_size != expected_size
        ):
            raise ValueError("Latest backup archive size is invalid")
        completed_at = payload.get("completed_at")
        if not isinstance(completed_at, str):
            raise ValueError("Latest backup completion time is invalid")
        parsed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Latest backup completion time has no timezone")
        return parsed

    async def aclose(self) -> None:
        try:
            await self._http.aclose()
        finally:
            try:
                await self._redis.aclose()
            finally:
                await self._database.dispose()
