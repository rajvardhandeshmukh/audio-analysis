"""Jobs routes — full CRUD + pipeline status + retry.

GET    /api/v1/jobs             list (VIEWER+)
GET    /api/v1/jobs/{id}        detail (VIEWER+)
POST   /api/v1/jobs             create manually (ANALYST+)
POST   /api/v1/jobs/{id}/retry  retry failed job (ANALYST+)
DELETE /api/v1/jobs/{id}        cancel/delete (ADMIN)
GET    /api/v1/jobs/{id}/transcript
GET    /api/v1/jobs/{id}/analysis
GET    /api/v1/jobs/{id}/report
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.application.services.audio_job_service import (
    AudioJobService,
    CreateAudioJobCommand,
)
from src.domain.enums.job_status import JobStatus
from src.domain.enums.user_role import UserRole
from src.domain.errors.domain_errors import (
    AnalysisNotFoundError,
    ReportNotFoundError,
    TranscriptNotFoundError,
)
from src.infrastructure.container import RepositoryContainer, ServiceContainer
from src.presentation.api.dependencies import get_repos, get_services, require_role
from src.presentation.api.response import ApiResponse, PaginatedResponse

router = APIRouter(prefix="/jobs", tags=["Audio Jobs"])


# ─── Request schemas ──────────────────────────────────────────────────────────

class CreateJobRequest(BaseModel):
    source_id: UUID
    file_name: str
    original_path: str
    storage_path: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=ApiResponse[PaginatedResponse])
async def list_jobs(
    status: JobStatus | None = Query(default=None),
    source_id: UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    repos: RepositoryContainer = Depends(get_repos),
    payload: dict = Depends(require_role(UserRole.VIEWER)),  # type: ignore[type-arg]
) -> ApiResponse:  # type: ignore[type-arg]
    if source_id is not None:
        jobs = await repos.audio_job.list_by_source(source_id, limit=limit, offset=offset)
    elif status is not None:
        jobs = await repos.audio_job.list_by_status(status, limit=limit, offset=offset)
    else:
        jobs = await repos.audio_job.list_all(limit=limit, offset=offset)

    return ApiResponse.ok(
        PaginatedResponse.of(
            items=[j.model_dump() for j in jobs],
            total=len(jobs),
            limit=limit,
            offset=offset,
        )
    )


@router.get("/{job_id}", response_model=ApiResponse)
async def get_job(
    job_id: UUID,
    repos: RepositoryContainer = Depends(get_repos),
    payload: dict = Depends(require_role(UserRole.VIEWER)),  # type: ignore[type-arg]
) -> ApiResponse:  # type: ignore[type-arg]
    job = await repos.audio_job.get_by_id(job_id)
    from src.domain.errors.domain_errors import JobNotFoundError
    if not job:
        raise JobNotFoundError(f"Job {job_id} not found.")
    return ApiResponse.ok(job.model_dump())


@router.post("", response_model=ApiResponse, status_code=201)
async def create_job(
    body: CreateJobRequest,
    services: ServiceContainer = Depends(get_services),
    payload: dict = Depends(require_role(UserRole.ANALYST)),  # type: ignore[type-arg]
) -> ApiResponse:  # type: ignore[type-arg]
    from src.infrastructure.auth.jwt_service import JWTService
    from src.infrastructure.config.settings import get_auth_settings
    cmd = CreateAudioJobCommand(
        source_id=body.source_id,
        file_name=body.file_name,
        original_path=body.original_path,
        storage_path=body.storage_path,
    )
    job = await services.audio_job.create_job(cmd)
    return ApiResponse.ok(job.model_dump())


@router.post("/{job_id}/retry", response_model=ApiResponse)
async def retry_job(
    job_id: UUID,
    services: ServiceContainer = Depends(get_services),
    payload: dict = Depends(require_role(UserRole.ANALYST)),  # type: ignore[type-arg]
) -> ApiResponse:  # type: ignore[type-arg]
    job = await services.audio_job.retry_job(job_id)
    return ApiResponse.ok(job.model_dump())


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: UUID,
    repos: RepositoryContainer = Depends(get_repos),
    payload: dict = Depends(require_role(UserRole.ADMIN)),  # type: ignore[type-arg]
) -> None:
    await repos.audio_job.delete(job_id)


@router.get("/{job_id}/transcript", response_model=ApiResponse)
async def get_transcript(
    job_id: UUID,
    repos: RepositoryContainer = Depends(get_repos),
    payload: dict = Depends(require_role(UserRole.VIEWER)),  # type: ignore[type-arg]
) -> ApiResponse:  # type: ignore[type-arg]
    transcript = await repos.transcript.get_by_job_id(job_id)
    if not transcript:
        raise TranscriptNotFoundError(f"No transcript for job {job_id}.")
    return ApiResponse.ok(transcript.model_dump())


@router.get("/{job_id}/analysis", response_model=ApiResponse)
async def get_analysis(
    job_id: UUID,
    repos: RepositoryContainer = Depends(get_repos),
    payload: dict = Depends(require_role(UserRole.VIEWER)),  # type: ignore[type-arg]
) -> ApiResponse:  # type: ignore[type-arg]
    analysis = await repos.analysis.get_by_job_id(job_id)
    if not analysis:
        raise AnalysisNotFoundError(f"No analysis for job {job_id}.")
    return ApiResponse.ok(analysis.model_dump())


@router.get("/{job_id}/report", response_model=ApiResponse)
async def get_report(
    job_id: UUID,
    repos: RepositoryContainer = Depends(get_repos),
    payload: dict = Depends(require_role(UserRole.VIEWER)),  # type: ignore[type-arg]
) -> ApiResponse:  # type: ignore[type-arg]
    report = await repos.report.get_by_job_id(job_id)
    if not report:
        raise ReportNotFoundError(f"No report for job {job_id}.")
    return ApiResponse.ok(report.model_dump())
