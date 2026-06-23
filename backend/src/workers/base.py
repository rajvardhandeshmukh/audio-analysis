"""Base worker framework — abstract lifecycle, error handling, DLQ routing.

All workers inherit from BaseWorker. They only implement process().
The lifecycle (connect → consume → ack/nack → disconnect) is owned here.

Rule 8: Workers are stateless per message — fresh DB connection per message.
Rule 17: Catch specific error types — never bare except.
Rule 19: nack(requeue=False) routes to DLQ. No retry loops in code.
"""

import asyncio
import signal
import tempfile
import time
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from src.domain.errors.domain_errors import DomainError, MessagingError
from src.infrastructure.config.settings import get_rabbitmq_settings
from src.infrastructure.container import RepositoryContainer, build_repositories
from src.infrastructure.db.session import dispose_engine, get_engine
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.messaging.rabbitmq_consumer import RabbitMQConsumer
from src.infrastructure.messaging.rabbitmq_publisher import RabbitMQPublisher
from src.infrastructure.messaging.schemas import JobFailedMessage, JobProgressEvent
from src.infrastructure.cache.event_publisher import publish_progress

logger = get_logger(__name__)


class BaseWorker(ABC):
    """Abstract base for all pipeline workers.

    Lifecycle:
        startup() → consume loop → shutdown()

    Subclasses implement:
        queue_name()       — which queue to consume
        message_schema()   — Pydantic schema for deserialization
        process()          — business logic for one message
    """

    def __init__(self, publisher: RabbitMQPublisher) -> None:
        self._publisher = publisher
        self._running = False

    @property
    @abstractmethod
    def queue_name(self) -> str:
        """RabbitMQ queue this worker consumes."""
        ...

    @property
    @abstractmethod
    def message_schema(self) -> type[BaseModel]:
        """Pydantic schema for incoming messages."""
        ...

    @property
    @abstractmethod
    def worker_name(self) -> str:
        """Human-readable worker identifier for logging and events."""
        ...

    @abstractmethod
    async def process(
        self,
        message: BaseModel,
        repos: RepositoryContainer,
    ) -> None:
        """Process one message.

        Args:
            message: Deserialized, typed message from the queue.
            repos: Repository container for this message's DB connection.

        Raises:
            DomainError: Any domain error will nack the message to DLQ.
        """
        ...

    async def run(self) -> None:
        """Start the worker consume loop. Runs until SIGTERM/SIGINT."""
        self._running = True
        self._setup_signal_handlers()

        settings = get_rabbitmq_settings()
        consumer = await RabbitMQConsumer.create(
            rabbitmq_url=settings.rabbitmq_url,
            queue_name=self.queue_name,
            schema=self.message_schema,
        )

        logger.info("worker.started", worker=self.worker_name, queue=self.queue_name)

        try:
            async for message, ack in consumer.consume(self.queue_name):
                if not self._running:
                    await ack.nack(requeue=True)  # Graceful shutdown — requeue safely
                    break

                async with get_engine().connect() as conn:
                    repos = build_repositories(conn)
                    try:
                        start_time = time.perf_counter()
                        await self.process(message, repos)
                        duration_sec = round(time.perf_counter() - start_time, 2)
                        
                        logger.info(
                            "worker.process_completed",
                            worker=self.worker_name,
                            duration_sec=duration_sec,
                        )
                        await ack.ack()
                    except DomainError as exc:
                        logger.error(
                            "worker.domain_error",
                            worker=self.worker_name,
                            error_code=exc.code,
                            error=exc.message,
                        )
                        await ack.nack(requeue=False)  # → DLQ
                    except Exception as exc:
                        logger.error(
                            "worker.unexpected_error",
                            worker=self.worker_name,
                            error=str(exc),
                        )
                        await ack.nack(requeue=False)  # → DLQ
        finally:
            await consumer.close()
            await dispose_engine()
            logger.info("worker.stopped", worker=self.worker_name)

    def stop(self) -> None:
        """Signal the consume loop to stop gracefully."""
        self._running = False

    def _setup_signal_handlers(self) -> None:
        import os
        if os.name == 'nt':
            signal.signal(signal.SIGINT, lambda s, f: self.stop())
            signal.signal(signal.SIGTERM, lambda s, f: self.stop())
        else:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, self.stop)

    async def _emit_progress(
        self,
        job_id: Any,
        status: str,
        message: str | None = None,
    ) -> None:
        """Publish a progress event to Redis pub/sub (best-effort)."""
        event = JobProgressEvent(
            job_id=job_id,
            status=status,
            stage=self.worker_name,
            message=message,
        )
        await publish_progress(event)
