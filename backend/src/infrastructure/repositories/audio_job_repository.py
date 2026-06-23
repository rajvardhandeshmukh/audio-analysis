"""AudioJob repository — SQLAlchemy Core implementation.

Rule 4: Only this repository talks to audio_jobs table.
Rule 12: No business logic here — CRUD only.
Rule 20: exists_by_path_and_source() enables idempotency in WatcherService.
"""

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.domain.entities.audio_job import AudioJob
from src.domain.enums.job_status import JobStatus
from src.domain.errors.domain_errors import JobNotFoundError
from src.domain.ports.repositories import AudioJobRepository
from src.domain.value_objects.audio_metadata import AudioMetadata
from src.infrastructure.db.tables import audio_jobs_table
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def _row_to_entity(row: sa.engine.Row) -> AudioJob:  # type: ignore[type-arg]
    """Map a database row to an AudioJob domain entity."""
    metadata = None
    if row.metadata:
        metadata = AudioMetadata.model_validate(row.metadata)

    return AudioJob(
        id=row.id,
        source_id=row.source_id,
        status=JobStatus(row.status),
        file_name=row.file_name,
        original_path=row.original_path,
        storage_path=row.storage_path,
        metadata=metadata,
        error_message=row.error_message,
        retry_count=row.retry_count,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PostgresAudioJobRepository(AudioJobRepository):
    """PostgreSQL implementation of AudioJobRepository using SQLAlchemy Core."""

    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def create(self, job: AudioJob) -> AudioJob:
        stmt = (
            audio_jobs_table.insert()
            .values(
                id=job.id,
                source_id=job.source_id,
                status=job.status.value,
                file_name=job.file_name,
                original_path=job.original_path,
                storage_path=job.storage_path,
                metadata=job.metadata.model_dump() if job.metadata else None,
                error_message=job.error_message,
                retry_count=job.retry_count,
                created_by=job.created_by,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
            .returning(*audio_jobs_table.c)
        )
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        logger.info("audio_job.created", job_id=str(job.id))
        return _row_to_entity(row)  # type: ignore[arg-type]

    async def get_by_id(self, job_id: UUID) -> AudioJob | None:
        stmt = sa.select(audio_jobs_table).where(audio_jobs_table.c.id == job_id)
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        return _row_to_entity(row) if row else None

    async def update(self, job: AudioJob) -> AudioJob:
        stmt = (
            audio_jobs_table.update()
            .where(audio_jobs_table.c.id == job.id)
            .values(
                status=job.status.value,
                storage_path=job.storage_path,
                metadata=job.metadata.model_dump() if job.metadata else None,
                error_message=job.error_message,
                retry_count=job.retry_count,
                updated_at=job.updated_at,
            )
            .returning(*audio_jobs_table.c)
        )
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        if not row:
            raise JobNotFoundError(f"AudioJob {job.id} not found for update.")
        logger.info("audio_job.updated", job_id=str(job.id), status=job.status.value)
        return _row_to_entity(row)

    async def delete(self, job_id: UUID) -> None:
        stmt = audio_jobs_table.delete().where(audio_jobs_table.c.id == job_id)
        await self._conn.execute(stmt)
        logger.info("audio_job.deleted", job_id=str(job_id))

    async def list_by_status(
        self, status: JobStatus, limit: int = 100, offset: int = 0
    ) -> list[AudioJob]:
        stmt = (
            sa.select(audio_jobs_table)
            .where(audio_jobs_table.c.status == status.value)
            .order_by(audio_jobs_table.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._conn.execute(stmt)
        return [_row_to_entity(row) for row in result.fetchall()]

    async def list_by_source(
        self, source_id: UUID, limit: int = 100, offset: int = 0
    ) -> list[AudioJob]:
        stmt = (
            sa.select(audio_jobs_table)
            .where(audio_jobs_table.c.source_id == source_id)
            .order_by(audio_jobs_table.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._conn.execute(stmt)
        return [_row_to_entity(row) for row in result.fetchall()]

    async def exists_by_path_and_source(
        self, original_path: str, source_id: UUID
    ) -> bool:
        stmt = sa.select(
            sa.exists().where(
                sa.and_(
                    audio_jobs_table.c.original_path == original_path,
                    audio_jobs_table.c.source_id == source_id,
                )
            )
        )
        result = await self._conn.execute(stmt)
        return bool(result.scalar())

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[AudioJob]:
        stmt = (
            sa.select(audio_jobs_table)
            .order_by(audio_jobs_table.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._conn.execute(stmt)
        return [_row_to_entity(row) for row in result.fetchall()]
