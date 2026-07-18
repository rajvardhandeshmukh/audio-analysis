"""Repository port interfaces — abstractions for all data persistence.

These ABCs live in domain/ports/ so the domain layer defines the contract.
Infrastructure implements them (Rule 2 — dependencies flow inward only).

Rule 4: Only repositories talk to the database.
Rule 12: Repositories are data access only — no business logic.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.analysis import Analysis
from src.domain.entities.audio_job import AudioJob
from src.domain.entities.job_event import JobEvent
from src.domain.entities.report import Report
from src.domain.entities.transcript import Transcript
from src.domain.entities.user import User
from src.domain.entities.watcher_source import WatcherSource
from src.domain.enums.job_status import JobStatus


class AudioJobRepository(ABC):
    """Persistence interface for AudioJob entities."""

    @abstractmethod
    async def create(self, job: AudioJob) -> AudioJob: ...

    @abstractmethod
    async def get_by_id(self, job_id: UUID) -> AudioJob | None: ...

    @abstractmethod
    async def update(self, job: AudioJob) -> AudioJob: ...

    @abstractmethod
    async def delete(self, job_id: UUID) -> None: ...

    @abstractmethod
    async def list_by_status(
        self, status: JobStatus, limit: int = 100, offset: int = 0
    ) -> list[AudioJob]: ...

    @abstractmethod
    async def list_by_source(
        self, source_id: UUID, limit: int = 100, offset: int = 0
    ) -> list[AudioJob]: ...

    @abstractmethod
    async def exists_by_path_and_source(
        self, original_path: str, source_id: UUID
    ) -> bool:
        """Idempotency check — returns True if this file was already queued."""
        ...

    @abstractmethod
    async def exists_by_hash(
        self, file_hash: str, source_id: UUID | None = None
    ) -> bool:
        """Idempotency check — returns True if a file with this hash was already queued."""
        ...

    @abstractmethod
    async def list_all(self, limit: int = 100, offset: int = 0) -> list[AudioJob]:
        """List all jobs regardless of status or source."""
        ...


class TranscriptRepository(ABC):
    """Persistence interface for Transcript entities."""

    @abstractmethod
    async def create(self, transcript: Transcript) -> Transcript: ...

    @abstractmethod
    async def get_by_id(self, transcript_id: UUID) -> Transcript | None: ...

    @abstractmethod
    async def get_by_job_id(self, job_id: UUID) -> Transcript | None: ...

    @abstractmethod
    async def update(self, transcript: Transcript) -> Transcript: ...

    @abstractmethod
    async def delete(self, transcript_id: UUID) -> None: ...


class AnalysisRepository(ABC):
    """Persistence interface for Analysis entities."""

    @abstractmethod
    async def create(self, analysis: Analysis) -> Analysis: ...

    @abstractmethod
    async def get_by_id(self, analysis_id: UUID) -> Analysis | None: ...

    @abstractmethod
    async def get_by_job_id(self, job_id: UUID) -> Analysis | None: ...

    @abstractmethod
    async def update(self, analysis: Analysis) -> Analysis: ...

    @abstractmethod
    async def delete(self, analysis_id: UUID) -> None: ...


class ReportRepository(ABC):
    """Persistence interface for Report entities."""

    @abstractmethod
    async def create(self, report: Report) -> Report: ...

    @abstractmethod
    async def get_by_id(self, report_id: UUID) -> Report | None: ...

    @abstractmethod
    async def get_by_job_id(self, job_id: UUID) -> Report | None: ...

    @abstractmethod
    async def delete(self, report_id: UUID) -> None: ...


class WatcherSourceRepository(ABC):
    """Persistence interface for WatcherSource entities."""

    @abstractmethod
    async def create(self, source: WatcherSource) -> WatcherSource: ...

    @abstractmethod
    async def get_by_id(self, source_id: UUID) -> WatcherSource | None: ...

    @abstractmethod
    async def list_all(self) -> list[WatcherSource]: ...

    @abstractmethod
    async def list_active(self) -> list[WatcherSource]: ...

    @abstractmethod
    async def update(self, source: WatcherSource) -> WatcherSource: ...

    @abstractmethod
    async def delete(self, source_id: UUID) -> None: ...


class UserRepository(ABC):
    """Persistence interface for User entities."""

    @abstractmethod
    async def create(self, user: User) -> User: ...

    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> User | None: ...

    @abstractmethod
    async def get_by_email(self, email: str) -> User | None: ...


    @abstractmethod
    async def update(self, user: User) -> User: ...

    @abstractmethod
    async def delete(self, user_id: UUID) -> None: ...


class JobEventRepository(ABC):
    """Persistence interface for JobEvent entities.

    Append-only — no update() or delete() methods.
    Job events are immutable audit records.
    """

    @abstractmethod
    async def create(self, event: JobEvent) -> JobEvent: ...

    @abstractmethod
    async def list_by_job_id(self, job_id: UUID) -> list[JobEvent]: ...

    @abstractmethod
    async def get_latest_by_job_id(self, job_id: UUID) -> JobEvent | None:
        """Return the most recent event for a job, ordered by occurred_at desc."""
        ...

