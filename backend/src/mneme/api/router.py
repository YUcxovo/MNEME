"""Top-level API router."""

from fastapi import APIRouter

from mneme.api.routes.digests import router as digests_router
from mneme.api.routes.events import router as events_router
from mneme.api.routes.graphs import router as graphs_router
from mneme.api.routes.health import router as health_router
from mneme.api.routes.jobs import router as jobs_router
from mneme.api.routes.onboarding import router as onboarding_router
from mneme.api.routes.papers import router as papers_router
from mneme.api.routes.preferences import router as preferences_router
from mneme.api.routes.qa import router as qa_router
from mneme.api.routes.summaries import router as summaries_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(jobs_router)
api_router.include_router(onboarding_router)
api_router.include_router(papers_router)
api_router.include_router(preferences_router)
api_router.include_router(summaries_router)
api_router.include_router(qa_router)
api_router.include_router(digests_router)
api_router.include_router(events_router)
api_router.include_router(graphs_router)
