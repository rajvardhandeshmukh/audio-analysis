"""JobEvent repository — PostgreSQL implementation using SQLAlchemy Core.

Append-only. No update or delete operations.
Rule 12: No business logic — persistence only.
"""

from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.domain.entities.job_event import JobEvent
from src.domain.enums.job_status import JobStatus
from src.domain.ports.repositories import JobEventRepository
from src.infrastructure.db.tables import job_events_table
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def _row_to_entity(row: sa.engine.Row) -> JobEvent:  # type: ignore[type-arg]
    return JobEvent(
        id=row.id,
        job_id=row.job_id,
        event_type=row.event_type,
        old_status=JobStatus(row.old_status) if row.old_status else None,
        new_status=JobStatus(row.new_status),
        worker=row.worker,
        message=row.message,
        metadata=row.metadata,
        occurred_at=row.occurred_at,
    )


class PostgresJobEventRepository(JobEventRepository):
    """PostgreSQL implementation of JobEventRepository — append-only audit log."""

    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def create(self, event: JobEvent) -> JobEvent:
        stmt = (
            job_events_table.insert()
            .values(
                id=event.id,
                job_id=event.job_id,
                event_type=event.event_type,
                old_status=event.old_status.value if event.old_status else None,
                new_status=event.new_status.value,
                worker=event.worker,
                message=event.message,
                metadata=event.metadata,
                occurred_at=event.occurred_at,
            )
            .returning(*job_events_table.c)
        )
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        logger.info(
            "job_event.created",
            job_id=str(event.job_id),
            event_type=event.event_type,
            new_status=event.new_status.value,
        )
        return _row_to_entity(row)  # type: ignore[arg-type]

    async def list_by_job_id(self, job_id: UUID) -> list[JobEvent]:
        stmt = (
            sa.select(job_events_table)
            .where(job_events_table.c.job_id == job_id)
            .order_by(job_events_table.c.occurred_at.asc())
        )
        result = await self._conn.execute(stmt)
        return [_row_to_entity(row) for row in result.fetchall()]

    async def get_latest_by_job_id(self, job_id: UUID) -> JobEvent | None:
        stmt = (
            sa.select(job_events_table)
            .where(job_events_table.c.job_id == job_id)
            .order_by(job_events_table.c.occurred_at.desc())
            .limit(1)
        )
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        return _row_to_entity(row) if row else None
