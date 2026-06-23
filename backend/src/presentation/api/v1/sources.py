"""Sources routes — CRUD for WatcherSource registry.

GET    /api/v1/sources          list (ANALYST+)
GET    /api/v1/sources/{id}     detail (ANALYST+)
POST   /api/v1/sources          create (ADMIN)
PATCH  /api/v1/sources/{id}     update (ADMIN)
DELETE /api/v1/sources/{id}     delete (ADMIN)
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.domain.entities.watcher_source import WatcherSource
from src.domain.enums.user_role import UserRole
from src.domain.errors.domain_errors import SourceNotFoundError
from src.infrastructure.container import RepositoryContainer
from src.presentation.api.dependencies import get_jwt_service, get_repos, get_current_user_payload, require_role
from src.presentation.api.response import ApiResponse

router = APIRouter(prefix="/sources", tags=["Sources"])


from src.domain.enums.source_type import SourceType

class CreateSourceRequest(BaseModel):
    name: str
    source_type: SourceType
    path: str
    file_patterns: list[str] = ["*.mp3", "*.wav", "*.m4a"]

class UpdateSourceRequest(BaseModel):
    name: str | None = None
    file_patterns: list[str] | None = None
    is_active: bool | None = None


@router.get("", response_model=ApiResponse)
async def list_sources(
    repos: RepositoryContainer = Depends(get_repos),
    payload: dict = Depends(require_role(UserRole.ANALYST)),  # type: ignore[type-arg]
) -> ApiResponse:  # type: ignore[type-arg]
    sources = await repos.watcher_source.list()
    return ApiResponse.ok([s.model_dump() for s in sources])


@router.get("/{source_id}", response_model=ApiResponse)
async def get_source(
    source_id: UUID,
    repos: RepositoryContainer = Depends(get_repos),
    payload: dict = Depends(require_role(UserRole.ANALYST)),  # type: ignore[type-arg]
) -> ApiResponse:  # type: ignore[type-arg]
    source = await repos.watcher_source.get_by_id(source_id)
    if not source:
        raise SourceNotFoundError(f"Source {source_id} not found.")
    return ApiResponse.ok(source.model_dump())


@router.post("", response_model=ApiResponse, status_code=201)
async def create_source(
    body: CreateSourceRequest,
    repos: RepositoryContainer = Depends(get_repos),
    payload: dict = Depends(require_role(UserRole.ADMIN)),  # type: ignore[type-arg]
    jwt_service=Depends(get_jwt_service),
) -> ApiResponse:  # type: ignore[type-arg]
    from src.infrastructure.auth.jwt_service import JWTService
    user_id = jwt_service.get_user_id(payload)
    source = WatcherSource(
        name=body.name,
        source_type=body.source_type,
        path=body.path,
        file_patterns=body.file_patterns,
        created_by=user_id,
    )
    saved = await repos.watcher_source.create(source)
    return ApiResponse.ok(saved.model_dump())


@router.patch("/{source_id}", response_model=ApiResponse)
async def update_source(
    source_id: UUID,
    body: UpdateSourceRequest,
    repos: RepositoryContainer = Depends(get_repos),
    payload: dict = Depends(require_role(UserRole.ADMIN)),  # type: ignore[type-arg]
) -> ApiResponse:  # type: ignore[type-arg]
    source = await repos.watcher_source.get_by_id(source_id)
    if not source:
        raise SourceNotFoundError(f"Source {source_id} not found.")
    if body.name is not None:
        source.name = body.name
    if body.file_patterns is not None:
        source.file_patterns = body.file_patterns
    if body.is_active is not None:
        source.is_active = body.is_active
    updated = await repos.watcher_source.update(source)
    return ApiResponse.ok(updated.model_dump())


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: UUID,
    repos: RepositoryContainer = Depends(get_repos),
    payload: dict = Depends(require_role(UserRole.ADMIN)),  # type: ignore[type-arg]
) -> None:
    await repos.watcher_source.delete(source_id)
