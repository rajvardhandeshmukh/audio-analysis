"""Redis async client factory.

Rule 9: No shared mutable state — get_redis() creates a connection on demand.
One connection pool per process, created at startup and shared via module-level singleton.
"""

from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from src.infrastructure.config.settings import get_redis_settings
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    global _pool  # noqa: PLW0603
    if _pool is None:
        settings = get_redis_settings()
        _pool = ConnectionPool.from_url(
            str(settings.redis_url),
            max_connections=20,
            decode_responses=True,
        )
        logger.info("redis.pool_created")
    return _pool


def get_redis() -> Redis:  # type: ignore[type-arg]
    """Return a Redis client using the shared connection pool."""
    return Redis(connection_pool=_get_pool())


async def close_pool() -> None:
    """Disconnect the pool on shutdown."""
    global _pool  # noqa: PLW0603
    if _pool:
        await _pool.aclose()
        _pool = None
        logger.info("redis.pool_closed")
