"""Typed message schemas for all queue stages.

Rule 15: Every queue message must have a Pydantic schema.
Never pass raw dicts to queues.

Message flow:
    IngestionMessage -> STTCompletedMessage -> RepairCompletedMessage
    -> AnalysisCompletedMessage -> ReportCompletedMessage

On failure at any stage: JobFailedMessage -> DLQ
"""

from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, Field


class IngestionMessage(BaseModel):
    """Published to ingestion_queue when a new audio file is detected.

    Published by: WatcherService / upload endpoint
    Consumed by:  STT Worker
    """

    job_id: UUID
    source_id: UUID
    file_name: str
    original_path: str
    storage_path: str = Field(..., description="Path in object storage after ingestion")
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class STTCompletedMessage(BaseModel):
    """Published to transcript_repair_queue after successful STT.

    Published by: STT Worker
    Consumed by:  Repair Worker
    """

    job_id: UUID
    transcript_id: UUID
    storage_path: str = Field(..., description="Object storage path for audio file")
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RepairCompletedMessage(BaseModel):
    """Published to behavioral_analysis_queue after transcript repair + diarization.

    Published by: Repair Worker
    Consumed by:  Analysis Worker
    """

    job_id: UUID
    transcript_id: UUID
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AnalysisCompletedMessage(BaseModel):
    """Published to report_queue after behavioral analysis.

    Published by: Analysis Worker
    Consumed by:  Report Worker
    """

    job_id: UUID
    analysis_id: UUID
    transcript_id: UUID
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReportCompletedMessage(BaseModel):
    """Published to Redis job_events channel after report generation.

    Published by: Report Worker
    Consumed by:  WebSocket Service (Redis Pub/Sub)
    """

    job_id: UUID
    report_id: UUID
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class JobFailedMessage(BaseModel):
    """Published to DLQ when a worker encounters an unrecoverable error.

    Published by: Any worker on fatal failure
    Consumed by:  DLQ monitor / alerting
    """

    job_id: UUID
    stage: str = Field(..., description="Queue stage where failure occurred")
    error_code: str
    error_message: str
    failed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class JobProgressEvent(BaseModel):
    """Real-time progress event published to Redis Pub/Sub.

    Published by: Every worker at stage transitions
    Consumed by:  WebSocket Service -> Frontend
    """

    job_id: UUID
    status: str = Field(..., description="New JobStatus value")
    stage: str = Field(..., description="Current pipeline stage")
    message: str | None = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
