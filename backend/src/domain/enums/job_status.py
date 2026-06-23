"""Job status enumeration for the audio processing pipeline."""

from enum import StrEnum


class JobStatus(StrEnum):
    """Represents the current stage of an audio analysis job.

    Transitions:
        PENDING -> INGESTING -> STT -> REPAIRING -> ANALYZING -> REPORTING -> COMPLETED
        Any stage -> FAILED (terminal, retriable via retry_job use case)
    """

    PENDING = "pending"
    INGESTING = "ingesting"
    STT = "stt"
    REPAIRING = "repairing"
    ANALYZING = "analyzing"
    REPORTING = "reporting"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        """Returns True if this status ends the pipeline (no further transitions)."""
        return self in (JobStatus.COMPLETED, JobStatus.FAILED)

    @property
    def is_active(self) -> bool:
        """Returns True if a worker is currently processing this job."""
        return self not in (
            JobStatus.PENDING,
            JobStatus.COMPLETED,
            JobStatus.FAILED,
        )

    def next_stage(self) -> "JobStatus":
        """Returns the expected next status in the happy path.

        Raises:
            ValueError: If called on a terminal status.
        """
        _transitions: dict["JobStatus", "JobStatus"] = {
            JobStatus.PENDING: JobStatus.INGESTING,
            JobStatus.INGESTING: JobStatus.STT,
            JobStatus.STT: JobStatus.REPAIRING,
            JobStatus.REPAIRING: JobStatus.ANALYZING,
            JobStatus.ANALYZING: JobStatus.REPORTING,
            JobStatus.REPORTING: JobStatus.COMPLETED,
        }
        if self.is_terminal:
            raise ValueError(f"Status '{self}' has no next stage — it is terminal.")
        return _transitions[self]
