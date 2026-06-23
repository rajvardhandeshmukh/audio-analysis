"""Repair Worker — consumes stt_queue, repairs transcript, diarizes speakers.

Pipeline stage: STT → REPAIRING
"""

from uuid import UUID

from pydantic import BaseModel

from src.domain.enums.job_status import JobStatus
from src.domain.errors.domain_errors import JobNotFoundError, TranscriptNotFoundError
from src.infrastructure.container import RepositoryContainer
from src.infrastructure.messaging.queue_config import QueueNames
from src.infrastructure.messaging.schemas import RepairCompletedMessage, STTCompletedMessage
from src.infrastructure.logging.logger import get_logger
from src.workers.base import BaseWorker

logger = get_logger(__name__)


class RepairWorker(BaseWorker):
    """Repair Worker — LLM transcript correction and GPT-4o speaker diarization."""

    def __init__(self, publisher, repair_provider) -> None:  # type: ignore[type-arg]
        super().__init__(publisher)
        self._repair = repair_provider

    @property
    def queue_name(self) -> str:
        return QueueNames.STT

    @property
    def message_schema(self) -> type[BaseModel]:
        return STTCompletedMessage

    @property
    def worker_name(self) -> str:
        return "repair_worker"

    async def process(self, message: BaseModel, repos: RepositoryContainer) -> None:
        msg = STTCompletedMessage.model_validate(message.model_dump())
        job_id: UUID = msg.job_id

        job = await repos.audio_job.get_by_id(job_id)
        if not job:
            raise JobNotFoundError(f"Job {job_id} not found in Repair worker.")

        transcript = await repos.transcript.get_by_id(msg.transcript_id)
        if not transcript:
            raise TranscriptNotFoundError(f"Transcript {msg.transcript_id} not found.")

        job.advance_to(JobStatus.REPAIRING)
        await repos.audio_job.update(job)
        await self._emit_progress(job_id, JobStatus.REPAIRING.value, "Repairing transcript")

        audio_metadata = job.metadata
        if not audio_metadata:
            from src.domain.value_objects.audio_metadata import AudioMetadata
            audio_metadata = AudioMetadata(
                format="unknown",
                duration_seconds=0.0,
                sample_rate=0,
                channels=1,
                bitrate_kbps=0,
                file_size_bytes=0,
            )

        repaired_text = await self._repair.repair_transcript(
            raw_text=transcript.raw_text,
            audio_metadata=audio_metadata,
        )
        transcript.apply_repair(repaired_text)

        await self._emit_progress(job_id, JobStatus.REPAIRING.value, "Diarizing speakers")
        segments = await self._repair.diarize(transcript, audio_metadata)
        transcript.apply_diarization(segments)

        await repos.transcript.update(transcript)
        await repos.commit()

        next_msg = RepairCompletedMessage(
            job_id=job_id,
            transcript_id=transcript.id,
        )
        await self._publisher.publish(QueueNames.TRANSCRIPT_REPAIR, next_msg)
        await self._emit_progress(job_id, JobStatus.REPAIRING.value, "Repair complete")
        logger.info(
            "repair_worker.done",
            job_id=str(job_id),
            segments=len(segments),
        )
