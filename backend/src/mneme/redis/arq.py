"""Shared ARQ connection settings derived from application configuration."""

from math import ceil

from arq.connections import RedisSettings

from mneme.core.config import Settings


def create_arq_redis_settings(settings: Settings) -> RedisSettings:
    """Preserve Redis auth, TLS, database, timeout, and pool bounds for ARQ."""
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
