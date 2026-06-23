"""Async database session factory — SQLAlchemy Core + asyncpg.

Rule 4: Only repositories use this session. Never inject into services/routes/workers.
Repositories receive a session via dependency injection — never create their own.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    create_async_engine,
)

from src.infrastructure.config.settings import DatabaseSettings, get_db_settings


def build_engine(settings: DatabaseSettings | None = None) -> AsyncEngine:
    """Create and return the async SQLAlchemy engine.

    Args:
        settings: Database settings. Uses cached settings if not provided.

    Returns:
        Configured AsyncEngine instance.
    """
    cfg = settings or get_db_settings()
    return create_async_engine(
        str(cfg.database_url),
        pool_size=cfg.db_pool_size,
        max_overflow=cfg.db_max_overflow,
        pool_timeout=cfg.db_pool_timeout,
        pool_pre_ping=True,   # Detect stale connections
        echo=False,            # Set True temporarily for SQL debugging only
    )


# Module-level engine — created once at startup, reused across requests
_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    """Return the module-level engine, creating it if necessary."""
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = build_engine()
    return _engine


async def get_connection() -> AsyncGenerator[AsyncConnection, None]:
    """Async generator that yields a database connection.

    Used as a FastAPI dependency. Each request gets its own connection.
    Repositories receive this connection — they do NOT create sessions.

    Usage in FastAPI:
        async def route(conn: AsyncConnection = Depends(get_connection)):
            repo = AudioJobRepository(conn)

    Raises:
        SQLAlchemyError: On connection failure.
    """
    async with get_engine().connect() as connection:
        try:
            yield connection
            await connection.commit()
        except Exception:
            await connection.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose the engine connection pool on application shutdown."""
    global _engine  # noqa: PLW0603
    if _engine is not None:
        await _engine.dispose()
        _engine = None
