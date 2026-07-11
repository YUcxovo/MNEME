"""FastAPI application entry point."""

from fastapi import FastAPI

from mneme.api.router import api_router


def create_app() -> FastAPI:
    """Create and configure the Mneme FastAPI application."""
    application = FastAPI(
        title="Mneme API",
        version="0.1.0",
        description="Backend API for the Mneme research assistant.",
    )
    application.include_router(api_router, prefix="/v1")
    return application


app = create_app()
