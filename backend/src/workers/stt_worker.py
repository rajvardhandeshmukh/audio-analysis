"""STT Worker — consumes ingestion_queue, transcribes audio, publishes to stt_queue.

Pipeline stage: PENDING → INGESTING → STT
"""

import os
import tempfile
from uuid import UUID

from pydantic import BaseModel

from src.domain.enums.job_status import JobStatus
from src.domain.errors.domain_errors import JobNotFoundError, STTProviderError
from src.infrastructure.container import RepositoryContainer
from src.infrastructure.messaging.queue_config import QueueNames
from src.infrastructure.messaging.schemas import IngestionMessage, STTCompletedMessage
from src.infrastructure.logging.logger import get_logger
from src.workers.base import BaseWorker

logger = get_logger(__name__)


class STTWorker(BaseWorker):
    """STT Worker — downloads audio, extracts metadata, transcribes, stores transcript."""

    def __init__(self, publisher, stt_provider, storage_provider) -> None:  # type: ignore[type-arg]
        super().__init__(publisher)
        self._stt = stt_provider
        self._storage = storage_provider

    @property
    def queue_name(self) -> str:
        return QueueNames.INGESTION

    @property
    def message_schema(self) -> type[BaseModel]:
        return IngestionMessage

    @property
    def worker_name(self) -> str:
        return "stt_worker"

    async def process(self, message: BaseModel, repos: RepositoryContainer) -> None:
        msg = IngestionMessage.model_validate(message.model_dump())
        job_id: UUID = msg.job_id

        job = await repos.audio_job.get_by_id(job_id)
        if not job:
            raise JobNotFoundError(f"Job {job_id} not found in STT worker.")

        job.advance_to(JobStatus.INGESTING)
        await repos.audio_job.update(job)
        await self._emit_progress(job_id, JobStatus.INGESTING.value, "Downloading audio")

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = os.path.join(tmpdir, msg.file_name)
            await self._storage.download(msg.storage_path, local_path)

            metadata = await self._stt.extract_metadata(local_path)
            job.attach_metadata(metadata)

            job.advance_to(JobStatus.STT)
            await repos.audio_job.update(job)
            await self._emit_progress(job_id, JobStatus.STT.value, "Transcribing audio")

            raw_text, language, confidence, word_timestamps = await self._stt.transcribe(
                local_path
            )

        from src.domain.entities.transcript import Transcript

        transcript = Transcript(
            job_id=job_id,
            raw_text=raw_text,
            language=language,
            confidence=confidence,
            word_timestamps=word_timestamps,
        )
        saved = await repos.transcript.create(transcript)

        next_msg = STTCompletedMessage(
            job_id=job_id,
            transcript_id=saved.id,
            storage_path=msg.storage_path,
        )
        await self._publisher.publish(QueueNames.STT, next_msg)
        await self._emit_progress(job_id, JobStatus.STT.value, "STT complete")
        logger.info("stt_worker.done", job_id=str(job_id), transcript_id=str(saved.id))
