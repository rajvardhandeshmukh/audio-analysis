"""JobEventService — records job lifecycle events and publishes real-time progress.

Business logic only. No SQL. No RabbitMQ.
Depends on: JobEventRepository (port), RedisEventPublisher (port).

Rule 13: Services contain business logic only.
Rule 7: Single responsibility — this service only manages job events.
"""

from uuid import UUID

from src.domain.entities.job_event import JobEvent, JobEventType
from src.domain.enums.job_status import JobStatus
from src.domain.ports.repositories import JobEventRepository
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class JobEventService:
    """Records job state transitions and returns the event history.

    Does not write to the database directly — delegates to JobEventRepository.
    Does not know about RabbitMQ or Redis — that is handled by the caller or
    infrastructure layer.
    """

    def __init__(self, event_repo: JobEventRepository) -> None:
        self._event_repo = event_repo

    async def record_status_change(
        self,
        job_id: UUID,
        old_status: JobStatus | None,
        new_status: JobStatus,
        worker: str | None = None,
        message: str | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> JobEvent:
        """Record a job status transition as an immutable event.

        Args:
            job_id: ID of the job that transitioned.
            old_status: Previous status. None for initial creation.
            new_status: New status after transition.
            worker: Identifier of the worker/service causing the transition.
            message: Optional context message.
            metadata: Optional structured context dictionary.

        Returns:
            Persisted JobEvent entity.
        """
        event_type = (
            JobEventType.JOB_CREATED
            if old_status is None
            else JobEventType.STATUS_CHANGED
        )
        if new_status == JobStatus.FAILED:
            event_type = JobEventType.ERROR_OCCURRED
        if new_status == JobStatus.COMPLETED:
            event_type = JobEventType.JOB_COMPLETED

        event = JobEvent(
            job_id=job_id,
            event_type=event_type,
            old_status=old_status,
            new_status=new_status,
            worker=worker,
            message=message,
            metadata=metadata,
        )

        persisted = await self._event_repo.create(event)
        logger.info(
            "job_event.recorded",
            job_id=str(job_id),
            event_type=event_type,
            old_status=old_status.value if old_status else None,
            new_status=new_status.value,
            worker=worker,
        )
        return persisted

    async def record_retry(
        self,
        job_id: UUID,
        retry_count: int,
        triggered_by: str,
    ) -> JobEvent:
        """Record a manual retry event.

        Args:
            job_id: ID of the job being retried.
            retry_count: New retry count after this retry.
            triggered_by: User ID or service name triggering the retry.

        Returns:
            Persisted JobEvent entity.
        """
        event = JobEvent(
            job_id=job_id,
            event_type=JobEventType.RETRY_TRIGGERED,
            old_status=JobStatus.FAILED,
            new_status=JobStatus.PENDING,
            worker=triggered_by,
            message=f"Retry #{retry_count} triggered by {triggered_by}",
            metadata={"retry_count": retry_count},
        )
        persisted = await self._event_repo.create(event)
        logger.info(
            "job_event.retry_recorded",
            job_id=str(job_id),
            retry_count=retry_count,
            triggered_by=triggered_by,
        )
        return persisted

    async def get_history(self, job_id: UUID) -> list[JobEvent]:
        """Return full ordered event history for a job.

        Args:
            job_id: ID of the job.

        Returns:
            List of JobEvent entities ordered by occurred_at ascending.
        """
        return await self._event_repo.list_by_job_id(job_id)
