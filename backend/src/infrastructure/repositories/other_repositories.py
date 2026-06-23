"""Report, WatcherSource, and User repositories — SQLAlchemy Core implementations."""

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.domain.entities.report import Report
from src.domain.entities.user import User
from src.domain.entities.watcher_source import WatcherSource
from src.domain.enums.source_type import SourceType
from src.domain.enums.user_role import UserRole
from src.domain.errors.domain_errors import (
    ReportNotFoundError,
    SourceNotFoundError,
    UserNotFoundError,
)
from src.domain.ports.repositories import (
    ReportRepository,
    UserRepository,
    WatcherSourceRepository,
)
from src.infrastructure.db.tables import (
    audio_sources_table,
    reports_table,
    users_table,
)
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


# ─── Report Repository ────────────────────────────────────────────────────────

def _report_row_to_entity(row: sa.engine.Row) -> Report:  # type: ignore[type-arg]
    return Report(
        id=row.id,
        job_id=row.job_id,
        analysis_id=row.analysis_id,
        transcript_id=row.transcript_id,
        title=row.title,
        storage_path=row.storage_path,
        overall_score=row.overall_score,
        call_duration_seconds=row.call_duration_seconds,
        compliance_passed=row.compliance_passed,
        agent_sentiment=row.agent_sentiment,
        customer_sentiment=row.customer_sentiment,
        summary=row.summary,
        generated_at=row.generated_at,
    )


class PostgresReportRepository(ReportRepository):
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def create(self, report: Report) -> Report:
        stmt = (
            reports_table.insert()
            .values(
                id=report.id,
                job_id=report.job_id,
                analysis_id=report.analysis_id,
                transcript_id=report.transcript_id,
                title=report.title,
                storage_path=report.storage_path,
                overall_score=report.overall_score,
                call_duration_seconds=report.call_duration_seconds,
                compliance_passed=report.compliance_passed,
                agent_sentiment=report.agent_sentiment,
                customer_sentiment=report.customer_sentiment,
                summary=report.summary,
                generated_at=report.generated_at,
            )
            .returning(*reports_table.c)
        )
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        logger.info("report.created", report_id=str(report.id), job_id=str(report.job_id))
        return _report_row_to_entity(row)  # type: ignore[arg-type]

    async def get_by_id(self, report_id: UUID) -> Report | None:
        stmt = sa.select(reports_table).where(reports_table.c.id == report_id)
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        return _report_row_to_entity(row) if row else None

    async def get_by_job_id(self, job_id: UUID) -> Report | None:
        stmt = sa.select(reports_table).where(reports_table.c.job_id == job_id)
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        return _report_row_to_entity(row) if row else None

    async def delete(self, report_id: UUID) -> None:
        stmt = reports_table.delete().where(reports_table.c.id == report_id)
        await self._conn.execute(stmt)


# ─── WatcherSource Repository ─────────────────────────────────────────────────

def _source_row_to_entity(row: sa.engine.Row) -> WatcherSource:  # type: ignore[type-arg]
    return WatcherSource(
        id=row.id,
        name=row.name,
        source_type=SourceType(row.source_type),
        path=row.path,
        file_patterns=list(row.file_patterns or []),
        is_active=row.is_active,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PostgresWatcherSourceRepository(WatcherSourceRepository):
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def create(self, source: WatcherSource) -> WatcherSource:
        stmt = (
            audio_sources_table.insert()
            .values(
                id=source.id,
                name=source.name,
                source_type=source.source_type.value,
                path=source.path,
                file_patterns=source.file_patterns,
                is_active=source.is_active,
                created_by=source.created_by,
                created_at=source.created_at,
                updated_at=source.updated_at,
            )
            .returning(*audio_sources_table.c)
        )
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        logger.info("watcher_source.created", source_id=str(source.id))
        return _source_row_to_entity(row)  # type: ignore[arg-type]

    async def get_by_id(self, source_id: UUID) -> WatcherSource | None:
        stmt = sa.select(audio_sources_table).where(audio_sources_table.c.id == source_id)
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        return _source_row_to_entity(row) if row else None

    async def list_active(self) -> list[WatcherSource]:
        stmt = (
            sa.select(audio_sources_table)
            .where(audio_sources_table.c.is_active == sa.true())
            .order_by(audio_sources_table.c.created_at.asc())
        )
        result = await self._conn.execute(stmt)
        return [_source_row_to_entity(row) for row in result.fetchall()]

    async def update(self, source: WatcherSource) -> WatcherSource:
        stmt = (
            audio_sources_table.update()
            .where(audio_sources_table.c.id == source.id)
            .values(
                name=source.name,
                path=source.path,
                file_patterns=source.file_patterns,
                is_active=source.is_active,
                updated_at=source.updated_at,
            )
            .returning(*audio_sources_table.c)
        )
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        if not row:
            raise SourceNotFoundError(f"WatcherSource {source.id} not found for update.")
        return _source_row_to_entity(row)

    async def delete(self, source_id: UUID) -> None:
        stmt = audio_sources_table.delete().where(audio_sources_table.c.id == source_id)
        await self._conn.execute(stmt)


# ─── User Repository ──────────────────────────────────────────────────────────

def _user_row_to_entity(row: sa.engine.Row) -> User:  # type: ignore[type-arg]
    return User(
        id=row.id,
        email=row.email,
        hashed_password=row.hashed_password,
        role=UserRole(row.role),
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PostgresUserRepository(UserRepository):
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def create(self, user: User) -> User:
        stmt = (
            users_table.insert()
            .values(
                id=user.id,
                email=str(user.email),
                hashed_password=user.hashed_password,
                role=user.role.value,
                is_active=user.is_active,
                created_at=user.created_at,
                updated_at=user.updated_at,
            )
            .returning(*users_table.c)
        )
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        logger.info("user.created", user_id=str(user.id), email=str(user.email))
        return _user_row_to_entity(row)  # type: ignore[arg-type]

    async def get_by_id(self, user_id: UUID) -> User | None:
        stmt = sa.select(users_table).where(users_table.c.id == user_id)
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        return _user_row_to_entity(row) if row else None

    async def get_by_email(self, email: str) -> User | None:
        stmt = sa.select(users_table).where(users_table.c.email == email)
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        return _user_row_to_entity(row) if row else None

    async def update(self, user: User) -> User:
        stmt = (
            users_table.update()
            .where(users_table.c.id == user.id)
            .values(
                role=user.role.value,
                is_active=user.is_active,
                updated_at=user.updated_at,
            )
            .returning(*users_table.c)
        )
        result = await self._conn.execute(stmt)
        row = result.fetchone()
        if not row:
            raise UserNotFoundError(f"User {user.id} not found for update.")
        return _user_row_to_entity(row)

    async def delete(self, user_id: UUID) -> None:
        stmt = users_table.delete().where(users_table.c.id == user_id)
        await self._conn.execute(stmt)
