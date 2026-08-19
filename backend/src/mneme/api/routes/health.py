"""Service health endpoint."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from redis.asyncio import Redis

from mneme.api.errors import ApiError, ErrorResponse
from mneme.core.config import Settings
from mneme.db.dependencies import get_database
from mneme.db.session import Database
from mneme.redis.dependencies import get_redis

router = APIRouter(tags=["health"])
logger = structlog.get_logger(__name__)

DependencyState = Literal["ready", "unavailable"]


class Health(BaseModel):
    """Public health-check response."""

    status: Literal["ok"]


class ReadinessDependencies(BaseModel):
    """Public status of each required runtime dependency."""

    postgresql: DependencyState
    redis: DependencyState


class Readiness(BaseModel):
    """Successful readiness response."""

    status: Literal["ready"]
    dependencies: ReadinessDependencies


@router.get("/health", response_model=Health, operation_id="getHealth")
async def get_health() -> Health:
    """Report that the application process is available."""
    return Health(status="ok")


def get_readiness_settings(request: Request) -> Settings:
    """Return the application settings used to bound readiness probes."""
    settings: Settings = request.app.state.settings
    return settings


async def _probe_dependency(
    name: str,
    probe: Callable[[], Awaitable[object]],
    timeout_seconds: float,
) -> DependencyState:
    try:
        async with asyncio.timeout(timeout_seconds):
            await probe()
    except Exception as error:
        logger.warning(
            "readiness_dependency_unavailable",
            dependency=name,
            exception_type=type(error).__name__,
        )
        return "unavailable"
    return "ready"


async def _ping_redis(redis: Redis) -> None:
    if not await redis.ping():
        raise RuntimeError("Redis did not acknowledge the readiness probe")


async def get_readiness_dependencies(
    database: Annotated[Database, Depends(get_database)],
    redis: Annotated[Redis, Depends(get_redis)],
    settings: Annotated[Settings, Depends(get_readiness_settings)],
) -> ReadinessDependencies:
    """Probe PostgreSQL and Redis concurrently within a strict time bound."""
    postgresql_state, redis_state = await asyncio.gather(
        _probe_dependency("postgresql", database.ping, settings.readiness_timeout_seconds),
        _probe_dependency(
            "redis",
            lambda: _ping_redis(redis),
            settings.readiness_timeout_seconds,
        ),
    )
    return ReadinessDependencies(postgresql=postgresql_state, redis=redis_state)


@router.get(
    "/health/ready",
    response_model=Readiness,
    operation_id="getReadiness",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse}},
)
async def get_readiness(
    dependencies: Annotated[ReadinessDependencies, Depends(get_readiness_dependencies)],
) -> Readiness:
    """Report whether all required persistence and queue dependencies are available."""
    if "unavailable" in (dependencies.postgresql, dependencies.redis):
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "service_unavailable",
            "A required service is temporarily unavailable.",
            details={"dependencies": dependencies.model_dump()},
        )
    return Readiness(status="ready", dependencies=dependencies)
