"""ARQ worker entry point and shared worker configuration."""

from math import ceil
from typing import Any, ClassVar

import structlog
from arq.connections import RedisSettings

from mneme.core.config import Settings, get_settings
from mneme.core.logging import configure_logging

logger = structlog.get_logger(__name__)


def create_arq_redis_settings(settings: Settings) -> RedisSettings:
    """Translate the validated application Redis URL into ARQ settings."""
    redis_url = settings.redis_url
    database = int((redis_url.path or "/0").removeprefix("/") or "0")
    return RedisSettings(
        host=redis_url.host or "localhost",
        port=redis_url.port or 6379,
        database=database,
        username=redis_url.username,
        password=redis_url.password,
        ssl=redis_url.scheme == "rediss",
        conn_timeout=max(1, ceil(settings.redis_socket_timeout_seconds)),
        max_connections=settings.redis_max_connections,
    )


async def worker_probe(_: dict[str, Any]) -> str:
    """Return a deterministic result for worker smoke tests."""
    return "ok"


async def on_startup(context: dict[str, Any]) -> None:
    """Configure the standalone worker process and shared context."""
    settings = get_settings()
    configure_logging(settings)
    context["settings"] = settings
    logger.info("worker_started", queue=settings.arq_queue_name)


async def on_shutdown(context: dict[str, Any]) -> None:
    """Record a clean worker shutdown."""
    settings: Settings = context.get("settings", get_settings())
    logger.info("worker_stopped", queue=settings.arq_queue_name)


_settings = get_settings()


class WorkerSettings:
    """Configuration loaded by the ARQ command-line worker."""

    functions: ClassVar = [worker_probe]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = create_arq_redis_settings(_settings)
    queue_name = _settings.arq_queue_name
    max_jobs = _settings.arq_max_jobs
    job_timeout = _settings.arq_job_timeout_seconds
    max_tries = _settings.arq_max_tries
    health_check_interval = _settings.arq_health_check_interval_seconds
    health_check_key = "mneme:worker:health"
