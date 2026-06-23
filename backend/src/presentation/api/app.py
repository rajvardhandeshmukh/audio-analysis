"""FastAPI application factory.

All wiring is done here: routers, lifespan, middleware, exception handlers.
Entry point: uvicorn src.presentation.api.app:create_app --factory
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.infrastructure.config.settings import get_app_settings
from src.infrastructure.db.session import dispose_engine
from src.infrastructure.cache.redis_client import close_pool
from src.infrastructure.logging.logger import get_logger
from src.presentation.api.error_handlers import register_handlers
from src.presentation.api.v1 import auth, jobs, sources, uploads
from src.presentation.websocket.server import ws_router

logger = get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("api.startup")
    yield
    await dispose_engine()
    await close_pool()
    logger.info("api.shutdown")


def create_app() -> FastAPI:
    """Application factory — call once at process startup."""
    settings = get_app_settings()

    app = FastAPI(
        title="Audio Analysis API",
        version="1.0.0",
        description=(
            "Call center audio processing pipeline — "
            "STT, transcript repair, speaker diarization, behavioral analysis."
        ),
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )

    # CORS — adjust origins in production via APP_CORS_ORIGINS env var
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Domain error → HTTP mapping
    register_handlers(app)

    # Routers
    _PREFIX = "/api/v1"
    app.include_router(auth.router, prefix=_PREFIX)
    app.include_router(jobs.router, prefix=_PREFIX)
    app.include_router(sources.router, prefix=_PREFIX)
    app.include_router(uploads.router, prefix=_PREFIX)
    app.include_router(ws_router)  # WebSocket at /ws

    @app.get("/health", tags=["Health"])
    async def health() -> dict:  # type: ignore[type-arg]
        return {"status": "ok", "service": "audio-analysis-api"}

    return app
