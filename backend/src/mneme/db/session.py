"""Async SQLAlchemy engine and session lifecycle."""

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def normalize_database_url(database_url: str) -> str:
    """Normalize common PostgreSQL URLs to SQLAlchemy's asyncpg dialect."""
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    raise ValueError("MNEME_DATABASE_URL must be a PostgreSQL URL")


class Database:
    """Own the async engine and create transaction-ready sessions."""

    def __init__(self, database_url: str, *, echo: bool = False) -> None:
        self.engine: AsyncEngine = create_async_engine(
            normalize_database_url(database_url),
            echo=echo,
            pool_pre_ping=True,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield one session and guarantee that it is closed after the request."""
        async with self.session_factory() as session:
            yield session

    async def ping(self) -> None:
        """Verify that PostgreSQL can execute a minimal query."""
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        """Release all pooled database connections during application shutdown."""
        await self.engine.dispose()
