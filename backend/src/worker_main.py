#!/usr/bin/env python3
"""Worker process entry point.

Usage:
    python -m src.worker_main stt
    python -m src.worker_main repair
    python -m src.worker_main analysis
    python -m src.worker_main report
    python -m src.worker_main watcher
"""

import asyncio
import os
import sys

# Ensure the backend root is in the Python path so absolute imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.infrastructure.config.settings import get_openai_settings, get_rabbitmq_settings, get_storage_settings
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.messaging.rabbitmq_publisher import RabbitMQPublisher
from src.infrastructure.providers.analysis.openai_analysis_provider import OpenAIAnalysisProvider
from src.infrastructure.providers.repair.openai_repair_provider import OpenAIRepairProvider
from src.infrastructure.providers.stt.openai_whisper_provider import OpenAIWhisperSTTProvider
from src.infrastructure.storage.minio_provider import MinioStorageProvider

logger = get_logger(__name__)


async def _run_worker(worker_type: str) -> None:
    settings = get_rabbitmq_settings()
    publisher = await RabbitMQPublisher.create(settings.rabbitmq_url)

    if worker_type == "stt":
        from src.workers.stt_worker import STTWorker
        storage = MinioStorageProvider.from_settings()
        stt = OpenAIWhisperSTTProvider.from_settings()
        worker = STTWorker(publisher=publisher, stt_provider=stt, storage_provider=storage)

    elif worker_type == "repair":
        from src.workers.repair_worker import RepairWorker
        repair = OpenAIRepairProvider.from_settings()
        worker = RepairWorker(publisher=publisher, repair_provider=repair)

    elif worker_type == "analysis":
        from src.workers.analysis_worker import AnalysisWorker
        analysis = OpenAIAnalysisProvider.from_settings()
        worker = AnalysisWorker(publisher=publisher, analysis_provider=analysis)

    elif worker_type == "report":
        from src.workers.report_worker import ReportWorker
        worker = ReportWorker(publisher=publisher)

    elif worker_type == "watcher":
        from src.infrastructure.config.settings import get_watcher_settings
        from src.workers.watcher.filesystem_watcher import FilesystemWatcherService
        from src.infrastructure.db.session import get_connection
        from src.infrastructure.container import build_repositories
        watcher_cfg = get_watcher_settings()
        storage = MinioStorageProvider.from_settings()
        async with (await get_connection()) as conn:
            repos = build_repositories(conn)
            sources = await repos.watcher_source.list()

        if not sources:
            logger.warning("watcher.no_sources_configured")
            return

        tasks = [
            FilesystemWatcherService(
                watch_dir=src.path,
                source_id=src.id,
                file_patterns=src.file_patterns,
                job_repo=None,  # type: ignore — created per-event inside service
                publisher=publisher,
                storage_provider=storage,
            ).run()
            for src in sources
            if src.is_active
        ]
        await asyncio.gather(*tasks)
        return

    else:
        logger.error("worker.unknown_type", type=worker_type)
        sys.exit(1)

    try:
        await worker.run()
    finally:
        await publisher.close()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m src.worker_main <stt|repair|analysis|report|watcher>")
        sys.exit(1)

    worker_type = sys.argv[1].lower()
    logger.info("worker.launching", type=worker_type)
    asyncio.run(_run_worker(worker_type))


if __name__ == "__main__":
    main()
