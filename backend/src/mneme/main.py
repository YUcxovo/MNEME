"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from redis.asyncio import Redis

from mneme.api.middleware import request_context_middleware
from mneme.api.router import api_router
from mneme.core.config import Settings, get_settings
from mneme.core.logging import configure_logging
from mneme.db import Database
from mneme.redis import create_redis_client

logger = structlog.get_logger(__name__)


def create_lifespan(settings: Settings, database: Database, redis_client: Redis):
    """Build an application lifespan bound to validated settings."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        logger.info(
            "application_started",
            environment=settings.environment.value,
            version=settings.app_version,
        )
        try:
            yield
        finally:
            try:
                await redis_client.aclose()
            finally:
                await database.dispose()
            logger.info("application_stopped")

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the Mneme FastAPI application."""
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings)
    database = Database(
        resolved_settings.database_url,
        echo=resolved_settings.debug,
    )
    redis_client = create_redis_client(resolved_settings)
    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        description="Backend API for the Mneme research assistant.",
        debug=resolved_settings.debug,
        lifespan=create_lifespan(resolved_settings, database, redis_client),
    )
    application.state.database = database
    application.state.redis = redis_client
    application.middleware("http")(request_context_middleware)
    application.include_router(api_router, prefix="/v1")
    return application


app = create_app()
