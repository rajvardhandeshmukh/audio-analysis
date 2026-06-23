"""AudioJobService — orchestrates the full audio job lifecycle.

Business logic only. No SQL. No direct RabbitMQ channel access.
Depends on: AudioJobRepository (port), JobEventService, MessagePublisher (port).

Rule 13: Services contain business logic only.
Rule 7: Single responsibility — job lifecycle only.
Rule 6: RabbitMQ is accessed via MessagePublisher abstraction only.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.entities.audio_job import AudioJob
from src.domain.enums.job_status import JobStatus
from src.domain.errors.domain_errors import (
    DuplicateJobError,
    JobNotFoundError,
)
from src.domain.ports.repositories import AudioJobRepository
from src.domain.ports.storage_messaging import MessagePublisher
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.messaging.queue_config import QueueNames
from src.infrastructure.messaging.schemas import IngestionMessage

from .job_event_service import JobEventService

logger = get_logger(__name__)


# ─── Command DTOs ─────────────────────────────────────────────────────────────
# Typed input contracts for service methods. Pydantic enforces structure (Rule 11).

class CreateAudioJobCommand(BaseModel):
    """Input contract for creating a new audio processing job."""

    source_id: UUID
    file_name: str = Field(..., min_length=1)
    original_path: str = Field(..., min_length=1)
    storage_path: str = Field(..., min_length=1)
    created_by: UUID | None = Field(
        default=None,
        description="Set when created via API upload. None when created by Watcher.",
    )


class RetryJobCommand(BaseModel):
    """Input contract for retrying a failed job."""

    job_id: UUID
    retried_by: UUID = Field(..., description="User ID or service name triggering retry")


class ListJobsQuery(BaseModel):
    """Query parameters for listing jobs."""

    status: JobStatus | None = Field(default=None)
    source_id: UUID | None = Field(default=None)
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


# ─── Service ──────────────────────────────────────────────────────────────────

class AudioJobService:
    """Manages the audio job lifecycle from creation through retry.

    Responsibilities:
        - Create jobs with idempotency check
        - Retry failed jobs
        - Retrieve and list jobs
        - Record lifecycle events via JobEventService
        - Publish messages to queue via MessagePublisher port

    Does NOT:
        - Execute SQL directly
        - Call RabbitMQ channel methods directly
        - Perform STT, repair, or analysis
    """

    def __init__(
        self,
        job_repo: AudioJobRepository,
        event_service: JobEventService,
        publisher: MessagePublisher,
    ) -> None:
        self._job_repo = job_repo
        self._event_service = event_service
        self._publisher = publisher

    async def create_job(self, cmd: CreateAudioJobCommand) -> AudioJob:
        """Create a new audio processing job and enqueue it for ingestion.

        Idempotent: raises DuplicateJobError if the same file+source already exists.

        Args:
            cmd: Typed command with all required fields.

        Returns:
            Persisted AudioJob entity in PENDING status.

        Raises:
            DuplicateJobError: If this file has already been queued from this source.
        """
        # Rule 20: Idempotency check before any write
        already_exists = await self._job_repo.exists_by_path_and_source(
            original_path=cmd.original_path,
            source_id=cmd.source_id,
        )
        if already_exists:
            raise DuplicateJobError(
                f"File '{cmd.file_name}' from source '{cmd.source_id}' "
                "has already been queued.",
                code="DUPLICATE_JOB",
            )

        job = AudioJob(
            source_id=cmd.source_id,
            file_name=cmd.file_name,
            original_path=cmd.original_path,
            storage_path=cmd.storage_path,
            created_by=cmd.created_by,
        )

        persisted_job = await self._job_repo.create(job)

        # Record creation event in audit log
        await self._event_service.record_status_change(
            job_id=persisted_job.id,
            old_status=None,
            new_status=JobStatus.PENDING,
            worker="audio_job_service",
            message=f"Job created for file '{cmd.file_name}'",
        )

        # Publish to ingestion queue via abstraction — never direct RabbitMQ call
        message = IngestionMessage(
            job_id=persisted_job.id,
            source_id=persisted_job.source_id,
            file_name=persisted_job.file_name,
            original_path=persisted_job.original_path,
            storage_path=persisted_job.storage_path,
        )
        await self._publisher.publish(queue_name=QueueNames.INGESTION, message=message)

        logger.info(
            "audio_job.created_and_enqueued",
            job_id=str(persisted_job.id),
            file_name=cmd.file_name,
            source_id=str(cmd.source_id),
        )
        return persisted_job

    async def retry_job(self, cmd: RetryJobCommand) -> AudioJob:
        """Retry a FAILED job by resetting its status and re-enqueuing.

        Args:
            cmd: Retry command with job_id and who triggered the retry.

        Returns:
            Updated AudioJob entity now in PENDING status.

        Raises:
            JobNotFoundError: If the job does not exist.
            InvalidJobTransitionError: If the job is not in FAILED status.
        """
        job = await self._job_repo.get_by_id(cmd.job_id)
        if not job:
            raise JobNotFoundError(f"AudioJob '{cmd.job_id}' not found.")

        # Domain entity enforces that only FAILED jobs can be retried
        job.increment_retry()
        updated_job = await self._job_repo.update(job)

        await self._event_service.record_retry(
            job_id=updated_job.id,
            retry_count=updated_job.retry_count,
            triggered_by=str(cmd.retried_by),
        )

        message = IngestionMessage(
            job_id=updated_job.id,
            source_id=updated_job.source_id,
            file_name=updated_job.file_name,
            original_path=updated_job.original_path,
            storage_path=updated_job.storage_path or "",
        )
        await self._publisher.publish(queue_name=QueueNames.INGESTION, message=message)

        logger.info(
            "audio_job.retry_enqueued",
            job_id=str(updated_job.id),
            retry_count=updated_job.retry_count,
            retried_by=str(cmd.retried_by),
        )
        return updated_job

    async def get_job(self, job_id: UUID) -> AudioJob:
        """Retrieve a single job by ID.

        Args:
            job_id: UUID of the job.

        Returns:
            AudioJob entity.

        Raises:
            JobNotFoundError: If not found.
        """
        job = await self._job_repo.get_by_id(job_id)
        if not job:
            raise JobNotFoundError(f"AudioJob '{job_id}' not found.")
        return job

    async def list_jobs(self, query: ListJobsQuery) -> list[AudioJob]:
        """List jobs filtered by status or source.

        Args:
            query: Filter and pagination parameters.

        Returns:
            List of AudioJob entities matching the query.
        """
        if query.source_id:
            return await self._job_repo.list_by_source(
                source_id=query.source_id,
                limit=query.limit,
                offset=query.offset,
            )
        if query.status:
            return await self._job_repo.list_by_status(
                status=query.status,
                limit=query.limit,
                offset=query.offset,
            )
        # Default: list all recent jobs
        return await self._job_repo.list_by_status(
            status=JobStatus.PENDING,
            limit=query.limit,
            offset=query.offset,
        )
