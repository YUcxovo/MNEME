"""Dependencies for citation-graph endpoints."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.core.config import Settings
from mneme.db.dependencies import get_database, get_session
from mneme.db.session import Database
from mneme.repositories.graph_preparation import GraphPreparationRepository
from mneme.repositories.graph_queries import SqlGraphRepository
from mneme.services.arxiv.client import ArxivClient
from mneme.services.graph import GraphService
from mneme.services.graph_preparation import GraphPreparationService
from mneme.services.openalex import OpenAlexClient
from mneme.services.seed_graph import SeedGraphCandidateService
from mneme.services.semantic_scholar import SemanticScholarClient


def get_graph_settings(request: Request) -> Settings:
    """Return the settings attached to the current FastAPI application."""
    settings: Settings = request.app.state.settings
    return settings


async def get_graph_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlGraphRepository:
    """Bind graph queries to the request session."""
    return SqlGraphRepository(session)


async def get_graph_service(
    repository: Annotated[SqlGraphRepository, Depends(get_graph_repository)],
) -> GraphService:
    """Build the public graph service from its persistence boundary."""
    return GraphService(repository)


async def get_graph_preparation_service(
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_graph_settings)],
) -> AsyncIterator[GraphPreparationService]:
    """Own external client lifetimes for one on-demand preparation request."""
    async with (
        ArxivClient(settings) as arxiv_client,
        SemanticScholarClient(settings) as semantic_client,
        OpenAlexClient(settings) as openalex_client,
    ):
        seed_graph_service = SeedGraphCandidateService(arxiv_client, semantic_client)
        yield GraphPreparationService(
            GraphPreparationRepository(database.session_factory),
            arxiv_client,
            seed_graph_service,
            openalex_client,
        )
