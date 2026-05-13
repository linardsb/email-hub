"""Database configuration and session management."""

import logging as stdlib_logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()


class _StructlogBridgeHandler(stdlib_logging.Handler):
    """Bridge stdlib `logging` records to structlog so redaction applies."""

    def emit(self, record: stdlib_logging.LogRecord) -> None:
        get_logger("sqlalchemy.engine").info(
            "sqlalchemy.engine.echo",
            message=record.getMessage(),
            level=record.levelname,
        )


def _route_sqlalchemy_to_structlog() -> None:
    """Re-emit `sqlalchemy.engine` logs via structlog so `redact_event_dict` runs.

    SQLAlchemy `echo=True` writes raw SQL (with bound parameter values that may
    contain PII) through stdlib `logging`, which bypasses the structlog
    processor chain. This routes those records back through structlog.
    """
    sa_logger = stdlib_logging.getLogger("sqlalchemy.engine")
    if any(isinstance(h, _StructlogBridgeHandler) for h in sa_logger.handlers):
        return
    sa_logger.handlers.clear()
    sa_logger.addHandler(_StructlogBridgeHandler())
    sa_logger.propagate = False


# Create async engine with connection pooling
engine = create_async_engine(
    settings.database.url,
    pool_pre_ping=True,
    pool_size=settings.database.pool_size,
    max_overflow=settings.database.pool_max_overflow,
    pool_recycle=settings.database.pool_recycle,
    echo=settings.database.echo,
)

if settings.database.echo:
    _route_sqlalchemy_to_structlog()

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for all database models."""


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Create a standalone async session for use outside FastAPI request lifecycle.

    Used by background tasks, agent tools, or CLI scripts that need DB access
    without a FastAPI request context.

    Yields:
        AsyncSession: Database session.
    """
    session = AsyncSessionLocal()
    try:
        yield session
    finally:
        await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides a database session.

    Yields:
        AsyncSession: Database session for the request.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
