"""Analysis repository — SQLAlchemy Core implementation."""

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.domain.entities.analysis import (
    Analysis,
    ComplianceFlag,
    ObjectionHandling,
    SentimentScore,
)
from src.domain.errors.domain_errors import AnalysisNotFoundError
from src.domain.ports.repositories import AnalysisRepository
from src.domain.value_objects.call_metrics import CallMetrics
from src.infrastructure.db.tables import analyses_table
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def _row_to_entity(row: sa.engine.Row) -> Analysis:  # type: ignore[type-arg]
    return Analysis(
        id=row.id,
        job_id=row.job_id,
        transcript_id=row.transcript_id,
        agent_performance_score=row.agent_performance_score,
        customer_satisfaction_score=row.customer_satisfaction_score,
        call_resolution_score=row.call_resolution_score,
        empathy_score=row.empathy_score,
        closing_effectiveness_score=row.closing_effectiveness_score,
        closing_signal_detected=row.closing_signal_detected,
        upsell_attempt_detected=row.upsell_attempt_detected,
        objection_handling=ObjectionHandling.model_validate(row.objection_handling),
        agent_sentiment=SentimentScore.model_validate(row.agent_sentiment),
        customer_sentiment=SentimentScore.model_validate(row.customer_sentiment),
        compliance_flags=[
            ComplianceFlag.model_validate(f) for f in (row.compliance_flags or [])
        ],
        compliance_passed=row.compliance_passed,
        call_metrics=CallMetrics.model_validate(row.call_metrics),
        summary=row.summary,
        strengths=row.strengths or [],
        improvement_areas=row.improvement_areas or [],
        recommendation=row.recommendation,
        coaching_notes=row.coaching_notes,
        created_at=row.created_at,
    )


class PostgresAnalysisRepository(AnalysisRepository):
    """PostgreSQL implementation of AnalysisRepository using SQLAlchemy Core."""

    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def create(self, analysis: Analysis) -> Analysis:
        stmt = (
            analyses_table.insert()
            .values(
                id=analysis.id,
                job_id=analysis.job_id,
                transcript_id=analysis.transcript_id,
                agent_performance_score=analysis.agent_performance_score,
                customer_satisfaction_score=analysis.customer_satisfaction_score,
                call_resolution_score=analysis.call_resolution_score,
                empathy_score=analysis.empathy_score,
                closing_effectiveness_score=analysis.closing_effectiveness_score,
                closing_signal_detected=analysis.closing_signal_detected,
                upsell_attempt_detected=analysis.upsell_attempt_detected,
                compliance_passed=analysis.compliance_passed,
                objection_handling=analysis.objection_handling.model_dump(),
                agent_sentiment=analysis.agent_sentiment.model_dump(),
                customer_sentiment=analysis.customer_sentiment.model_dump(),
                compliance_flags=[f.model_dump() for f in analysis.compliance_flags],
                call_metrics=analysis.call_metrics.model_dump(),
                summary=analysis.summary,
                strengths=analysis.strengths,
                improvement_areas=analysis.improvement_areas,
                recommendation=analysis.recommendation,
                coaching_notes=analysis.coaching_notes,
                created_at=analysis.created_at,
            )
            .returning(*analyses_table.c)
        )
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        logger.info("analysis.created", analysis_id=str(analysis.id), job_id=str(analysis.job_id))
        return _row_to_entity(row)  # type: ignore[arg-type]

    async def get_by_id(self, analysis_id: UUID) -> Analysis | None:
        stmt = sa.select(analyses_table).where(analyses_table.c.id == analysis_id)
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        return _row_to_entity(row) if row else None

    async def get_by_job_id(self, job_id: UUID) -> Analysis | None:
        stmt = sa.select(analyses_table).where(analyses_table.c.job_id == job_id)
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        return _row_to_entity(row) if row else None

    async def update(self, analysis: Analysis) -> Analysis:
        stmt = (
            analyses_table.update()
            .where(analyses_table.c.id == analysis.id)
            .values(
                coaching_notes=analysis.coaching_notes,
            )
            .returning(*analyses_table.c)
        )
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        if not row:
            raise AnalysisNotFoundError(f"Analysis {analysis.id} not found for update.")
        return _row_to_entity(row)

    async def delete(self, analysis_id: UUID) -> None:
        stmt = analyses_table.delete().where(analyses_table.c.id == analysis_id)
        await self._conn.execute(stmt)
