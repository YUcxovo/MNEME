"""Application-scoped asynchronous Redis client."""

from redis.asyncio import Redis

from mneme.core.config import Settings


def create_redis_client(settings: Settings) -> Redis:
    """Create a lazy Redis client with an application-scoped connection pool."""
    return Redis.from_url(
        str(settings.redis_url),
        decode_responses=True,
        max_connections=settings.redis_max_connections,
        socket_connect_timeout=settings.redis_socket_timeout_seconds,
        socket_timeout=settings.redis_socket_timeout_seconds,
    )
