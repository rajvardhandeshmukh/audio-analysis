"""JobEvent domain entity — immutable audit log of all job state transitions.

Written by workers and services on every status change.
Never mutated after creation. Append-only.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.domain.enums.job_status import JobStatus


class JobEvent(BaseModel):
    """Immutable record of a single event in a job's lifecycle.

    Created by JobEventService on every status transition.
    Stored in job_events table. Never updated or deleted.

    Attributes:
        event_type: Semantic label for the event e.g. 'status_changed', 'retry_triggered'.
        old_status: Job status before this event. None for the initial PENDING creation event.
        new_status: Job status after this event.
        worker: Identifier of the worker/service that produced this event.
        message: Optional human-readable context message.
        metadata: Optional structured context — worker-specific key/value pairs.
    """

    model_config = {"frozen": True}  # Immutable — audit log entries never change

    id: UUID = Field(default_factory=uuid4)
    job_id: UUID
    event_type: str = Field(..., min_length=1, max_length=100)
    old_status: JobStatus | None = Field(default=None)
    new_status: JobStatus
    worker: str | None = Field(default=None, max_length=100)
    message: str | None = Field(default=None)
    # Flexible context: kept as dict for audit purposes only.
    # Never process business logic from this field.
    metadata: dict[str, str | int | float | bool | None] | None = Field(default=None)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ─── Event type constants ──────────────────────────────────────────────────────

class JobEventType:
    """Semantic event type labels. Single source of truth — never hardcode strings."""

    JOB_CREATED = "job_created"
    STATUS_CHANGED = "status_changed"
    RETRY_TRIGGERED = "retry_triggered"
    ERROR_OCCURRED = "error_occurred"
    JOB_COMPLETED = "job_completed"
