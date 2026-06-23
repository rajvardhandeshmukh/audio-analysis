"""Analysis Worker — consumes transcript_repair_queue, runs GPT-4o behavioral analysis.

Pipeline stage: REPAIRING → ANALYZING
"""

from uuid import UUID

from pydantic import BaseModel

from src.domain.enums.job_status import JobStatus
from src.domain.errors.domain_errors import JobNotFoundError, TranscriptNotFoundError
from src.infrastructure.container import RepositoryContainer
from src.infrastructure.messaging.queue_config import QueueNames
from src.infrastructure.messaging.schemas import AnalysisCompletedMessage, RepairCompletedMessage
from src.infrastructure.logging.logger import get_logger
from src.workers.base import BaseWorker

logger = get_logger(__name__)


class AnalysisWorker(BaseWorker):
    """Analysis Worker — GPT-4o structured behavioral analysis of diarized transcript."""

    def __init__(self, publisher, analysis_provider) -> None:  # type: ignore[type-arg]
        super().__init__(publisher)
        self._analysis = analysis_provider

    @property
    def queue_name(self) -> str:
        return QueueNames.TRANSCRIPT_REPAIR

    @property
    def message_schema(self) -> type[BaseModel]:
        return RepairCompletedMessage

    @property
    def worker_name(self) -> str:
        return "analysis_worker"

    async def process(self, message: BaseModel, repos: RepositoryContainer) -> None:
        msg = RepairCompletedMessage.model_validate(message.model_dump())
        job_id: UUID = msg.job_id

        job = await repos.audio_job.get_by_id(job_id)
        if not job:
            raise JobNotFoundError(f"Job {job_id} not found in Analysis worker.")

        transcript = await repos.transcript.get_by_id(msg.transcript_id)
        if not transcript:
            raise TranscriptNotFoundError(f"Transcript {msg.transcript_id} not found.")

        job.advance_to(JobStatus.ANALYZING)
        await repos.audio_job.update(job)
        await self._emit_progress(job_id, JobStatus.ANALYZING.value, "Running behavioral analysis")

        from src.domain.value_objects.audio_metadata import AudioMetadata
        audio_metadata = job.metadata or AudioMetadata(
            format="unknown",
            duration_seconds=0.0,
            sample_rate=0,
            channels=1,
            bitrate_kbps=0,
            file_size_bytes=0,
        )

        analysis = await self._analysis.analyze(transcript, audio_metadata)
        saved = await repos.analysis.create(analysis)
        await repos.commit()

        next_msg = AnalysisCompletedMessage(
            job_id=job_id,
            analysis_id=saved.id,
            transcript_id=transcript.id,
        )
        await self._publisher.publish(QueueNames.BEHAVIORAL_ANALYSIS, next_msg)
        await self._emit_progress(job_id, JobStatus.ANALYZING.value, "Analysis complete")
        logger.info(
            "analysis_worker.done",
            job_id=str(job_id),
            analysis_id=str(saved.id),
            agent_score=saved.agent_performance_score,
        )
