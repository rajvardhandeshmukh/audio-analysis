"""FastAPI dependency providers — DB, auth, services, RBAC.

All Depends() targets live here. Route handlers import only from this module.
"""

from collections.abc import AsyncGenerator
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.application.services.audio_job_service import AudioJobService
from src.application.services.job_event_service import JobEventService
from src.domain.enums.user_role import UserRole
from src.domain.errors.domain_errors import AuthenticationError, AuthorizationError
from src.infrastructure.auth.jwt_service import JWTService
from src.infrastructure.config.settings import get_rabbitmq_settings, get_storage_settings, get_openai_settings
from src.infrastructure.container import (
    RepositoryContainer,
    ServiceContainer,
    build_repositories,
    build_services,
)
from src.infrastructure.db.session import get_connection
from src.infrastructure.messaging.rabbitmq_publisher import RabbitMQPublisher
from src.infrastructure.storage.minio_provider import MinioStorageProvider

_bearer = HTTPBearer(auto_error=False)


# ─── Singletons (created once at startup) ─────────────────────────────────────

@lru_cache(maxsize=1)
def get_jwt_service() -> JWTService:
    return JWTService.from_settings()


@lru_cache(maxsize=1)
def get_storage() -> MinioStorageProvider:
    return MinioStorageProvider.from_settings()


# ─── Per-request dependencies ─────────────────────────────────────────────────

async def get_repos(
    conn=Depends(get_connection),
) -> AsyncGenerator[RepositoryContainer, None]:
    yield build_repositories(conn)


async def get_publisher() -> AsyncGenerator[RabbitMQPublisher, None]:
    """Create a short-lived publisher for one request's publish calls."""
    settings = get_rabbitmq_settings()
    publisher = await RabbitMQPublisher.create(settings.rabbitmq_url)
    try:
        yield publisher
    finally:
        await publisher.close()


async def get_services(
    repos: RepositoryContainer = Depends(get_repos),
    publisher: RabbitMQPublisher = Depends(get_publisher),
) -> ServiceContainer:
    return build_services(repos, publisher)


# ─── Auth dependencies ────────────────────────────────────────────────────────

async def get_current_user_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    jwt_service: JWTService = Depends(get_jwt_service),
) -> dict:  # type: ignore[type-arg]
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NO_TOKEN", "message": "Bearer token required."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return jwt_service.decode_token(credentials.credentials)


def require_role(minimum_role: UserRole):  # type: ignore[return]
    """Factory that returns a FastAPI dependency enforcing a minimum role."""
    async def _check(
        payload: dict = Depends(get_current_user_payload),  # type: ignore[type-arg]
        jwt_service: JWTService = Depends(get_jwt_service),
    ) -> dict:  # type: ignore[type-arg]
        jwt_service.require_role(payload, minimum_role)
        return payload
    return _check
