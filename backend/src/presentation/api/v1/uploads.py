"""Upload routes — presigned URL generation for direct-to-MinIO uploads.

POST /api/v1/uploads/presign   → returns presigned PUT URL + storage_key
POST /api/v1/uploads/confirm   → creates a job after client confirms upload

Flow:
  1. Client calls /presign → gets {upload_url, storage_key}
  2. Client PUTs file directly to MinIO via upload_url
  3. Client calls /confirm with storage_key → AudioJob created, enqueued
"""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.domain.enums.user_role import UserRole
from src.infrastructure.config.settings import get_storage_settings
from src.infrastructure.container import ServiceContainer
from src.infrastructure.storage.minio_provider import MinioStorageProvider
from src.presentation.api.dependencies import (
    get_services,
    get_storage,
    require_role,
)
from src.presentation.api.response import ApiResponse
from src.application.services.audio_job_service import CreateAudioJobCommand

router = APIRouter(prefix="/uploads", tags=["Uploads"])


class PresignRequest(BaseModel):
    file_name: str
    source_id: UUID


class PresignResponse(BaseModel):
    upload_url: str
    storage_key: str
    expires_in: int


class ConfirmRequest(BaseModel):
    source_id: UUID
    file_name: str
    storage_key: str


@router.post("/presign", response_model=ApiResponse[PresignResponse])
async def presign_upload(
    body: PresignRequest,
    storage: MinioStorageProvider = Depends(get_storage),
    payload: dict = Depends(require_role(UserRole.ANALYST)),  # type: ignore[type-arg]
) -> ApiResponse[PresignResponse]:
    """Generate a presigned PUT URL for direct browser/client upload to MinIO."""
    unique_key = f"audio/{body.source_id}/{uuid4()}/{body.file_name}"
    from datetime import timedelta
    # Presigned PUT for client-side direct upload (3600s validity)
    upload_url = storage._client.presigned_put_object(
        storage._bucket, unique_key, expires=timedelta(seconds=3600)
    )
    return ApiResponse.ok(
        PresignResponse(upload_url=upload_url, storage_key=unique_key, expires_in=3600)
    )


@router.post("/confirm", response_model=ApiResponse, status_code=201)
async def confirm_upload(
    body: ConfirmRequest,
    services: ServiceContainer = Depends(get_services),
    payload: dict = Depends(require_role(UserRole.ANALYST)),  # type: ignore[type-arg]
) -> ApiResponse:  # type: ignore[type-arg]
    """Create an AudioJob and enqueue it after client confirms upload is done."""
    cmd = CreateAudioJobCommand(
        source_id=body.source_id,
        file_name=body.file_name,
        original_path=f"upload/{body.storage_key}",
        storage_path=body.storage_key,
    )
    job = await services.audio_job.create_job(cmd)
    return ApiResponse.ok(job.model_dump())
