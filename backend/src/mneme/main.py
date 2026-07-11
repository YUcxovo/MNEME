"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from mneme.api.middleware import request_context_middleware
from mneme.api.router import api_router
from mneme.core.config import Settings, get_settings
from mneme.core.logging import configure_logging

logger = structlog.get_logger(__name__)


def create_lifespan(settings: Settings):
    """Build an application lifespan bound to validated settings."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        logger.info(
            "application_started",
            environment=settings.environment.value,
            version=settings.app_version,
        )
        yield
        logger.info("application_stopped")

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the Mneme FastAPI application."""
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings)
    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        description="Backend API for the Mneme research assistant.",
        debug=resolved_settings.debug,
        lifespan=create_lifespan(resolved_settings),
    )
    application.middleware("http")(request_context_middleware)
    application.include_router(api_router, prefix="/v1")
    return application


app = create_app()
