"""FastAPI dependencies for Redis access."""

from fastapi import Request
from redis.asyncio import Redis


def get_redis(request: Request) -> Redis:
    """Return the application-scoped Redis client."""
    client: Redis = request.app.state.redis
    return client
