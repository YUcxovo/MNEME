"""Shared Redis connection infrastructure."""

from mneme.redis.client import create_redis_client

__all__ = ["create_redis_client"]
