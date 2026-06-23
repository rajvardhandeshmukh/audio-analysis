"""Transcript repository — SQLAlchemy Core implementation."""

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.domain.entities.transcript import Transcript
from src.domain.errors.domain_errors import TranscriptNotFoundError
from src.domain.ports.repositories import TranscriptRepository
from src.domain.value_objects.speaker_segment import SpeakerSegment
from src.domain.value_objects.word_timestamp import WordTimestamp
from src.infrastructure.db.tables import transcripts_table
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def _row_to_entity(row: sa.engine.Row) -> Transcript:  # type: ignore[type-arg]
    return Transcript(
        id=row.id,
        job_id=row.job_id,
        raw_text=row.raw_text,
        repaired_text=row.repaired_text,
        language=row.language,
        confidence=row.confidence,
        word_timestamps=[WordTimestamp.model_validate(w) for w in (row.word_timestamps or [])],
        segments=[SpeakerSegment.model_validate(s) for s in (row.segments or [])],
        is_repaired=row.is_repaired,
        is_diarized=row.is_diarized,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PostgresTranscriptRepository(TranscriptRepository):
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def create(self, transcript: Transcript) -> Transcript:
        stmt = (
            transcripts_table.insert()
            .values(
                id=transcript.id,
                job_id=transcript.job_id,
                raw_text=transcript.raw_text,
                repaired_text=transcript.repaired_text,
                language=transcript.language,
                confidence=transcript.confidence,
                word_timestamps=[w.model_dump() for w in transcript.word_timestamps],
                segments=[s.model_dump() for s in transcript.segments],
                is_repaired=transcript.is_repaired,
                is_diarized=transcript.is_diarized,
                created_at=transcript.created_at,
                updated_at=transcript.updated_at,
            )
            .returning(*transcripts_table.c)
        )
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        logger.info(
            "transcript.created",
            transcript_id=str(transcript.id),
            job_id=str(transcript.job_id),
        )
        return _row_to_entity(row)  # type: ignore[arg-type]

    async def get_by_id(self, transcript_id: UUID) -> Transcript | None:
        stmt = sa.select(transcripts_table).where(transcripts_table.c.id == transcript_id)
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        return _row_to_entity(row) if row else None

    async def get_by_job_id(self, job_id: UUID) -> Transcript | None:
        stmt = sa.select(transcripts_table).where(transcripts_table.c.job_id == job_id)
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        return _row_to_entity(row) if row else None

    async def update(self, transcript: Transcript) -> Transcript:
        stmt = (
            transcripts_table.update()
            .where(transcripts_table.c.id == transcript.id)
            .values(
                repaired_text=transcript.repaired_text,
                word_timestamps=[w.model_dump() for w in transcript.word_timestamps],
                segments=[s.model_dump() for s in transcript.segments],
                is_repaired=transcript.is_repaired,
                is_diarized=transcript.is_diarized,
                updated_at=transcript.updated_at,
            )
            .returning(*transcripts_table.c)
        )
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        if not row:
            raise TranscriptNotFoundError(f"Transcript {transcript.id} not found.")
        logger.info("transcript.updated", transcript_id=str(transcript.id))
        return _row_to_entity(row)

    async def delete(self, transcript_id: UUID) -> None:
        stmt = transcripts_table.delete().where(transcripts_table.c.id == transcript_id)
        await self._conn.execute(stmt)
