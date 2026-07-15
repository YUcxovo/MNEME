"""Repository dependencies for paper and preference endpoints."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.db.dependencies import get_session
from mneme.repositories.paper_catalog import PaperCatalogRepository
from mneme.repositories.preferences import PreferenceRepository


async def get_paper_catalog_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PaperCatalogRepository:
    """Bind a paper catalog repository to the request session."""
    return PaperCatalogRepository(session)


async def get_preference_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PreferenceRepository:
    """Bind a preference repository to the request session."""
    return PreferenceRepository(session)
