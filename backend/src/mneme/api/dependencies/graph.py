"""Dependencies for citation-graph endpoints."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.db.dependencies import get_session
from mneme.repositories.graph_queries import SqlGraphRepository
from mneme.services.graph import GraphService


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
