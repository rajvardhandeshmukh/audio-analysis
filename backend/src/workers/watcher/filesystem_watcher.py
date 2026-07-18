"""Filesystem Watcher Service — monitors directories for new audio files.

Uses watchdog for inotify/FSEvents/kqueue events.
On new file detection: deduplication check → upload to storage → create job → publish.

Rule 20: Idempotency via AudioJobRepository.exists_by_path_and_source().
"""

import asyncio
import os
import fnmatch
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from src.domain.errors.domain_errors import DuplicateJobError
from src.infrastructure.config.settings import get_watcher_settings
from src.infrastructure.logging.logger import get_logger
from src.workers.watcher.file_hasher import sha256

logger = get_logger(__name__)


class _AudioFileHandler(FileSystemEventHandler):
    """Watchdog event handler — enqueues new audio files into an asyncio queue."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue,  # type: ignore[type-arg]
        patterns: list[str],
    ) -> None:
        self._loop = loop
        self._queue = queue
        self._patterns = patterns

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        path = str(event.src_path)
        if any(fnmatch.fnmatch(os.path.basename(path), p) for p in self._patterns):
            self._loop.call_soon_threadsafe(self._queue.put_nowait, path)


class FilesystemWatcherService:
    """Monitors a local directory and triggers audio processing jobs.

    Designed to run as a long-lived async process alongside other workers.
    One instance per WatcherSource record.
    """

    def __init__(
        self,
        watch_dir: str,
        source_id: "UUID",  # type: ignore[name-defined]
        file_patterns: list[str],
        job_repo: "AudioJobRepository",  # type: ignore[name-defined]
        publisher: "MessagePublisher",  # type: ignore[name-defined]
        storage_provider: "StorageProvider",  # type: ignore[name-defined]
    ) -> None:
        self._watch_dir = watch_dir
        self._source_id = source_id
        self._file_patterns = file_patterns or ["*.mp3", "*.wav", "*.m4a", "*.ogg", "*.flac"]
        self._job_repo = job_repo
        self._publisher = publisher
        self._storage = storage_provider
        self._running = False
        self._seen_files: set[str] = set()

    def _scan_existing_files(self, queue: asyncio.Queue[str]) -> None:
        if not os.path.exists(self._watch_dir):
            os.makedirs(self._watch_dir, exist_ok=True)
            return
        current_files = set()
        for root, _, files in os.walk(self._watch_dir):
            for file in files:
                if any(fnmatch.fnmatch(file, p) for p in self._file_patterns):
                    full_path = os.path.join(root, file)
                    current_files.add(full_path)
                    if full_path not in self._seen_files:
                        self._seen_files.add(full_path)
                        queue.put_nowait(full_path)
        self._seen_files.intersection_update(current_files)

    async def run(self) -> None:
        """Start watching the configured directory. Runs until stopped."""
        self._running = True
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[str] = asyncio.Queue()

        os.makedirs(self._watch_dir, exist_ok=True)
        self._scan_existing_files(queue)

        handler = _AudioFileHandler(loop, queue, self._file_patterns)
        observer = Observer()
        observer.schedule(handler, self._watch_dir, recursive=False)
        observer.start()

        logger.info(
            "watcher.started",
            directory=self._watch_dir,
            source_id=str(self._source_id),
            patterns=self._file_patterns,
        )

        iterations = 0
        try:
            while self._running:
                iterations += 1
                if iterations >= 30:
                    iterations = 0
                    self._scan_existing_files(queue)
                try:
                    file_path = await asyncio.wait_for(queue.get(), timeout=1.0)
                    await self._handle_new_file(file_path)
                except asyncio.TimeoutError:
                    continue  # Normal — poll loop
        finally:
            observer.stop()
            observer.join()
            logger.info("watcher.stopped", directory=self._watch_dir)

    def stop(self) -> None:
        self._running = False

    async def _handle_new_file(self, file_path: str) -> None:
        """Process a newly detected audio file."""
        if not os.path.exists(file_path):
            return
        self._seen_files.add(file_path)
        file_name = os.path.basename(file_path)
        logger.info("watcher.file_detected", path=file_path)

        from src.application.services.audio_job_service import (
            AudioJobService,
            CreateAudioJobCommand,
        )
        from src.application.services.job_event_service import JobEventService
        from src.infrastructure.container import build_repositories
        from src.infrastructure.db.session import get_connection

        async with (await get_connection()) as conn:
            repos = build_repositories(conn)
            job_repo = repos.audio_job

            # Idempotency: check if path already queued
            already_queued = await job_repo.exists_by_path_and_source(
                original_path=file_path,
                source_id=self._source_id,
            )
            if already_queued:
                return

            # Compute SHA-256 and check hash idempotency
            try:
                file_hash = sha256(file_path)
            except OSError:
                return

            hash_queued = await job_repo.exists_by_hash(
                file_hash=file_hash,
                source_id=self._source_id,
            )
            if hash_queued:
                logger.info("watcher.duplicate_hash_skipped", path=file_path, hash=file_hash)
                return

            # Upload to object storage
            storage_key = f"audio/{self._source_id}/{file_hash}/{file_name}"
            await self._storage.upload(file_path, storage_key)

            job_event_service = JobEventService(event_repo=repos.job_event)
            audio_job_service = AudioJobService(
                job_repo=job_repo,
                event_service=job_event_service,
                publisher=self._publisher,
            )
            cmd = CreateAudioJobCommand(
                source_id=self._source_id,
                file_name=file_name,
                original_path=file_path,
                file_hash=file_hash,
                storage_path=storage_key,
            )
            try:
                job = await audio_job_service.create_job(cmd)
                logger.info(
                    "watcher.job_created",
                    job_id=str(job.id),
                    file=file_name,
                )
            except DuplicateJobError:
                logger.info("watcher.duplicate_skipped", path=file_path)


from uuid import UUID  # noqa: E402
from src.domain.ports.repositories import AudioJobRepository  # noqa: E402
from src.domain.ports.storage_messaging import MessagePublisher, StorageProvider  # noqa: E402
