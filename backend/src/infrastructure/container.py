"""Dependency injection container — wires repositories, services, and infrastructure.

Provides two usage patterns:
  1. FastAPI: use get_* async generator functions as Depends() targets.
  2. Workers: call build_service_container() once at startup.

Rule 9: No shared mutable state — each request/worker gets its own container instance.
Rule 2: Dependencies flow inward — container lives in infrastructure but imports
        domain ports and application services.
"""

from collections.abc import AsyncGenerator
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncConnection

from src.application.services.audio_job_service import AudioJobService
from src.application.services.job_event_service import JobEventService
from src.domain.ports.storage_messaging import MessagePublisher
from src.infrastructure.db.session import get_connection
from src.infrastructure.repositories.analysis_repository import PostgresAnalysisRepository
from src.infrastructure.repositories.audio_job_repository import PostgresAudioJobRepository
from src.infrastructure.repositories.job_event_repository import PostgresJobEventRepository
from src.infrastructure.repositories.other_repositories import (
    PostgresReportRepository,
    PostgresUserRepository,
    PostgresWatcherSourceRepository,
)
from src.infrastructure.repositories.transcript_repository import PostgresTranscriptRepository


@dataclass(frozen=True)
class RepositoryContainer:
    """Holds all repository instances for a single database connection.

    Immutable after construction — one instance per request or worker iteration.
    """

    audio_job: PostgresAudioJobRepository
    transcript: PostgresTranscriptRepository
    analysis: PostgresAnalysisRepository
    report: PostgresReportRepository
    watcher_source: PostgresWatcherSourceRepository
    user: PostgresUserRepository
    job_event: PostgresJobEventRepository

    async def commit(self) -> None:
        """Explicitly commit the underlying connection transaction."""
        await self.audio_job._conn.commit()


@dataclass(frozen=True)
class ServiceContainer:
    """Holds all application service instances.

    Built on top of RepositoryContainer. Immutable after construction.
    """

    audio_job: AudioJobService
    job_event: JobEventService


def build_repositories(conn: AsyncConnection) -> RepositoryContainer:
    """Instantiate all repositories for a given database connection.

    Args:
        conn: Open SQLAlchemy Core async connection. Managed externally.

    Returns:
        RepositoryContainer with all repositories sharing the same connection.
    """
    return RepositoryContainer(
        audio_job=PostgresAudioJobRepository(conn),
        transcript=PostgresTranscriptRepository(conn),
        analysis=PostgresAnalysisRepository(conn),
        report=PostgresReportRepository(conn),
        watcher_source=PostgresWatcherSourceRepository(conn),
        user=PostgresUserRepository(conn),
        job_event=PostgresJobEventRepository(conn),
    )


def build_services(
    repos: RepositoryContainer,
    publisher: MessagePublisher,
) -> ServiceContainer:
    """Instantiate all application services with their dependencies.

    Args:
        repos: Repository container (all repos sharing one DB connection).
        publisher: MessagePublisher port implementation (e.g. RabbitMQPublisher).

    Returns:
        ServiceContainer with all services wired to their dependencies.
    """
    job_event_service = JobEventService(event_repo=repos.job_event)

    audio_job_service = AudioJobService(
        job_repo=repos.audio_job,
        event_service=job_event_service,
        publisher=publisher,
    )

    return ServiceContainer(
        audio_job=audio_job_service,
        job_event=job_event_service,
    )


def build_service_container(
    conn: AsyncConnection,
    publisher: MessagePublisher,
) -> ServiceContainer:
    """One-shot factory — builds repos and services together.

    Use this in workers where you manage the connection lifecycle manually.

    Args:
        conn: Open SQLAlchemy Core async connection.
        publisher: MessagePublisher implementation.

    Returns:
        Fully wired ServiceContainer.
    """
    repos = build_repositories(conn)
    return build_services(repos, publisher)


# ─── FastAPI dependency providers ─────────────────────────────────────────────
# These are async generator functions used with FastAPI's Depends().
# Each request gets a fresh container with its own DB connection.

async def get_repository_container(
    conn: AsyncConnection,
) -> AsyncGenerator[RepositoryContainer, None]:
    """FastAPI dependency — yields a RepositoryContainer for the current request.

    Usage in route:
        async def route(repos: RepositoryContainer = Depends(get_repository_container)):
            job = await repos.audio_job.get_by_id(job_id)
    """
    yield build_repositories(conn)


async def get_service_container(
    conn: AsyncConnection,
    publisher: MessagePublisher,
) -> AsyncGenerator[ServiceContainer, None]:
    """FastAPI dependency — yields a ServiceContainer for the current request.

    Usage in route:
        async def route(services: ServiceContainer = Depends(get_service_container)):
            job = await services.audio_job.create_job(cmd)
    """
    yield build_service_container(conn, publisher)
