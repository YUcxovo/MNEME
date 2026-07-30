"""Async SQLAlchemy engine and session lifecycle."""

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from mneme.core.config import Settings


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

    def __init__(
        self,
        database_url: str,
        *,
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 5,
        pool_timeout_seconds: float = 30.0,
        pool_recycle_seconds: int = 1800,
    ) -> None:
        self.engine: AsyncEngine = create_async_engine(
            normalize_database_url(database_url),
            echo=echo,
            pool_pre_ping=True,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout_seconds,
            pool_recycle=pool_recycle_seconds,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @classmethod
    def from_settings(cls, settings: Settings, *, echo: bool | None = None) -> "Database":
        """Create a database container from the shared bounded pool settings."""
        return cls(
            settings.database_url,
            echo=settings.debug if echo is None else echo,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout_seconds=settings.database_pool_timeout_seconds,
            pool_recycle_seconds=settings.database_pool_recycle_seconds,
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
