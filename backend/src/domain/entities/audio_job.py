"""AudioJob domain entity.

Central aggregate of the audio processing pipeline.
Status transitions are enforced here — not in the service layer.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.domain.enums.job_status import JobStatus
from src.domain.errors.domain_errors import (
    InvalidJobTransitionError,
    JobAlreadyCompletedError,
)
from src.domain.value_objects.audio_metadata import AudioMetadata


class AudioJob(BaseModel):
    """Represents a single audio file processing job.

    Lifecycle:
        PENDING -> INGESTING -> STT -> REPAIRING -> ANALYZING -> REPORTING -> COMPLETED
        Any stage -> FAILED (via mark_failed)

    This entity owns the status transition logic. Services never set status directly.
    """

    model_config = {"frozen": False}  # Mutable entity — status transitions

    id: UUID = Field(default_factory=uuid4)
    source_id: UUID = Field(..., description="ID of the WatcherSource that produced this job")
    status: JobStatus = Field(default=JobStatus.PENDING)
    file_name: str = Field(..., min_length=1, description="Original audio file name")
    original_path: str = Field(..., description="Path on source filesystem")
    file_hash: str | None = Field(
        default=None, description="SHA-256 fingerprint of the audio file"
    )
    storage_path: str | None = Field(
        default=None, description="Path in object storage after ingestion"
    )
    metadata: AudioMetadata | None = Field(
        default=None, description="Extracted audio metadata (set during ingestion)"
    )
    error_message: str | None = Field(
        default=None, description="Last error message if status is FAILED"
    )
    retry_count: int = Field(default=0, ge=0, description="Number of retry attempts")
    created_by: UUID | None = Field(
        default=None, description="User ID if manually created; None if watcher-created"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # ─── Status Transition Methods ────────────────────────────────────────────

    def advance_to(self, new_status: JobStatus) -> None:
        """Transition this job to the next status in the pipeline.

        Args:
            new_status: The target status to transition into.

        Raises:
            JobAlreadyCompletedError: If the job is already in a terminal state.
            InvalidJobTransitionError: If the transition is not permitted.
        """
        if self.status.is_terminal:
            raise JobAlreadyCompletedError(
                f"Job {self.id} is in terminal state '{self.status}' "
                f"and cannot transition to '{new_status}'."
            )
        allowed_next = self.status.next_stage()
        if new_status != allowed_next and new_status != JobStatus.FAILED:
            raise InvalidJobTransitionError(
                f"Job {self.id}: cannot transition '{self.status}' -> '{new_status}'. "
                f"Expected next: '{allowed_next}'."
            )
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)

    def mark_failed(self, reason: str) -> None:
        """Mark this job as failed with a reason.

        Args:
            reason: Human-readable failure reason stored for debugging.
        """
        self.status = JobStatus.FAILED
        self.error_message = reason
        self.updated_at = datetime.now(timezone.utc)

    def increment_retry(self) -> None:
        """Increment retry counter and reset status to PENDING for re-queuing."""
        if not self.status.is_terminal:
            raise InvalidJobTransitionError(
                f"Can only retry a FAILED job. Current status: '{self.status}'."
            )
        self.retry_count += 1
        self.status = JobStatus.PENDING
        self.error_message = None
        self.updated_at = datetime.now(timezone.utc)

    def attach_metadata(self, metadata: AudioMetadata) -> None:
        """Set audio metadata discovered during ingestion."""
        self.metadata = metadata
        self.updated_at = datetime.now(timezone.utc)

    def attach_storage_path(self, path: str) -> None:
        """Set the object storage path after successful upload."""
        self.storage_path = path
        self.updated_at = datetime.now(timezone.utc)
