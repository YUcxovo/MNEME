"""Top-level API router."""

from fastapi import APIRouter

from mneme.api.routes.health import router as health_router
from mneme.api.routes.papers import router as papers_router
from mneme.api.routes.preferences import router as preferences_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(papers_router)
api_router.include_router(preferences_router)
