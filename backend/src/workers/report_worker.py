"""Report Worker — consumes behavioral_analysis_queue, generates Report, marks job COMPLETED.

Final pipeline stage: ANALYZING → REPORTING → COMPLETED
"""

from uuid import UUID

from pydantic import BaseModel

from src.domain.entities.report import Report
from src.domain.enums.job_status import JobStatus
from src.domain.errors.domain_errors import (
    AnalysisNotFoundError,
    JobNotFoundError,
    TranscriptNotFoundError,
)
from src.application.services.report_exporter import export_report_as_text
from src.infrastructure.container import RepositoryContainer
from src.infrastructure.messaging.queue_config import QueueNames
from src.infrastructure.messaging.schemas import AnalysisCompletedMessage, ReportCompletedMessage
from src.infrastructure.logging.logger import get_logger
from src.workers.base import BaseWorker

logger = get_logger(__name__)


class ReportWorker(BaseWorker):
    """Report Worker — assembles final Report from Analysis + Transcript, marks job COMPLETED."""

    @property
    def queue_name(self) -> str:
        return QueueNames.BEHAVIORAL_ANALYSIS

    @property
    def message_schema(self) -> type[BaseModel]:
        return AnalysisCompletedMessage

    @property
    def worker_name(self) -> str:
        return "report_worker"

    async def process(self, message: BaseModel, repos: RepositoryContainer) -> None:
        msg = AnalysisCompletedMessage.model_validate(message.model_dump())
        job_id: UUID = msg.job_id

        job = await repos.audio_job.get_by_id(job_id)
        if not job:
            raise JobNotFoundError(f"Job {job_id} not found in Report worker.")

        analysis = await repos.analysis.get_by_id(msg.analysis_id)
        if not analysis:
            raise AnalysisNotFoundError(f"Analysis {msg.analysis_id} not found.")

        transcript = await repos.transcript.get_by_id(msg.transcript_id)
        if not transcript:
            raise TranscriptNotFoundError(f"Transcript {msg.transcript_id} not found.")

        job.advance_to(JobStatus.REPORTING)
        await repos.audio_job.update(job)
        await self._emit_progress(job_id, JobStatus.REPORTING.value, "Generating report")

        overall_score = round(
            (
                analysis.agent_performance_score
                + analysis.customer_satisfaction_score
                + analysis.call_resolution_score
            )
            / 3,
            2,
        )

        report = Report(
            job_id=job_id,
            analysis_id=analysis.id,
            transcript_id=transcript.id,
            title=f"Call Analysis — {job.file_name}",
            overall_score=overall_score,
            call_duration_seconds=analysis.call_metrics.total_duration_seconds,
            compliance_passed=analysis.compliance_passed,
            agent_sentiment=analysis.agent_sentiment.overall,
            customer_sentiment=analysis.customer_sentiment.overall,
            summary=analysis.summary,
        )
        saved_report = await repos.report.create(report)

        try:
            exported_path = export_report_as_text(job=job, analysis=analysis, transcript=transcript)
            logger.info("report_worker.exported_text", path=exported_path)
        except Exception as e:
            logger.error("report_worker.export_failed", error=str(e))

        job.advance_to(JobStatus.COMPLETED)
        await repos.audio_job.update(job)
        await repos.commit()

        next_msg = ReportCompletedMessage(job_id=job_id, report_id=saved_report.id)
        await self._publisher.publish(QueueNames.REPORT, next_msg)
        await self._emit_progress(job_id, JobStatus.COMPLETED.value, "Processing complete")

        logger.info(
            "report_worker.done",
            job_id=str(job_id),
            report_id=str(saved_report.id),
            overall_score=overall_score,
        )
