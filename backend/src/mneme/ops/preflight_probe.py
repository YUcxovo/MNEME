"""Live dependency probes for the production preflight gate."""

import asyncio
import os
import re
import shutil
import subprocess
from pathlib import Path
from uuid import UUID

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from redis.asyncio import Redis
from sqlalchemy import text

from mneme.core.config import Settings
from mneme.db.session import Database
from mneme.ops.backup import BackupConfigurationError, validate_libpq_environment
from mneme.redis.client import create_redis_client

_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class ProductionPreflightProbe:
    """Probe configured production dependencies without exposing their addresses."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._database = Database.from_settings(settings, echo=False)
        self._redis: Redis = create_redis_client(settings)

    async def ping_database(self) -> bool:
        await self._database.ping()
        return True

    async def _scalar(self, statement: str, parameters: dict[str, object] | None = None) -> object:
        async with self._database.engine.connect() as connection:
            return await connection.scalar(text(statement), parameters or {})

    async def database_revision(self) -> str | None:
        value = await self._scalar("SELECT version_num FROM alembic_version")
        return str(value) if value is not None else None

    async def has_pgvector(self) -> bool:
        value = await self._scalar(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
        )
        return bool(value)

    async def demo_user_exists(self, user_id: UUID) -> bool:
        value = await self._scalar(
            "SELECT EXISTS (SELECT 1 FROM users WHERE id = :user_id)",
            {"user_id": user_id},
        )
        return bool(value)

    async def connection_limits(self) -> tuple[int, int, int]:
        maximum = int(str(await self._scalar("SHOW max_connections")))
        superuser_reserved = int(str(await self._scalar("SHOW superuser_reserved_connections")))
        reserved = int(str(await self._scalar("SHOW reserved_connections")))
        return maximum, superuser_reserved, reserved

    async def ping_redis(self) -> bool:
        return bool(await self._redis.ping())

    async def paper_storage_writable(self) -> bool:
        path = self._settings.paper_storage_dir
        return path.is_dir() and os.access(path, os.W_OK | os.X_OK)

    async def backup_tools_available(self) -> bool:
        return shutil.which("pg_dump") is not None and shutil.which("pg_restore") is not None

    async def backup_credentials_configured(self) -> bool:
        try:
            validate_libpq_environment(os.environ)
        except BackupConfigurationError:
            return False
        return True

    async def backup_target_matches_database(self) -> bool:
        """Verify the private libpq service reaches this application database."""
        user_id = self._settings.demo_user_id
        if user_id is None:
            return False
        try:
            validate_libpq_environment(os.environ)
        except BackupConfigurationError:
            return False
        query = _database_fingerprint_query(user_id)
        application_value = await self._scalar(query)
        application_fingerprint = str(application_value or "").strip()
        if not _FINGERPRINT_PATTERN.fullmatch(application_fingerprint):
            return False
        backup_fingerprint = await asyncio.to_thread(
            _read_backup_database_fingerprint,
            query,
            max(1.0, self._settings.readiness_timeout_seconds),
        )
        return backup_fingerprint == application_fingerprint

    async def aclose(self) -> None:
        await self._redis.aclose()
        await self._database.dispose()


def expected_migration_head(config_path: Path) -> str:
    """Read the single Alembic head required by this checkout."""
    heads = ScriptDirectory.from_config(AlembicConfig(str(config_path))).get_heads()
    if len(heads) != 1:
        raise ValueError("Mneme deployment requires exactly one migration head")
    return heads[0]


def _database_fingerprint_query(user_id: UUID) -> str:
    """Build a non-secret, restart-scoped database identity query."""
    return (
        "SELECT md5(concat_ws('|', current_database(), d.oid::text, "
        "pg_postmaster_start_time()::text, a.version_num, u.id::text)) "
        "FROM pg_database AS d CROSS JOIN alembic_version AS a "
        f"JOIN users AS u ON u.id = '{user_id}'::uuid "
        "WHERE d.datname = current_database()"
    )


def _read_backup_database_fingerprint(query: str, timeout_seconds: float) -> str | None:
    try:
        result = subprocess.run(
            (
                "psql",
                "-X",
                "--no-password",
                "--tuples-only",
                "--no-align",
                "--set=ON_ERROR_STOP=1",
                f"--command={query}",
            ),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    fingerprint = result.stdout.strip()
    if result.returncode != 0 or not _FINGERPRINT_PATTERN.fullmatch(fingerprint):
        return None
    return fingerprint
