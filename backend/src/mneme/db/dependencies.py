"""FastAPI dependencies for database access."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.db.session import Database


def get_database(request: Request) -> Database:
    """Return the application-scoped database container."""
    database: Database = request.app.state.database
    return database


async def get_session(
    database: Annotated[Database, Depends(get_database)],
) -> AsyncIterator[AsyncSession]:
    """Provide one async SQLAlchemy session per FastAPI dependency scope."""
    async for session in database.session():
        yield session
