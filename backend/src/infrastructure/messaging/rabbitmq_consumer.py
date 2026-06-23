"""RabbitMQ consumer — implements MessageConsumer and MessageAcknowledger ports.

Rule 6: This is the ONLY place that calls aio-pika ack/nack methods.
Workers receive messages via the MessageConsumer ABC — never touching aio-pika directly.
Rule 19: No retry loops in code — retries are handled by RabbitMQ DLQ policy.
Rule 20: Workers are responsible for idempotency — consumer does not deduplicate.
"""

from collections.abc import AsyncIterator
from typing import Any, TypeVar

import aio_pika
from pydantic import BaseModel, ValidationError

from src.domain.errors.domain_errors import MessageDeserializationError, MessagingError
from src.domain.ports.storage_messaging import MessageAcknowledger, MessageConsumer
from src.infrastructure.config.settings import get_rabbitmq_settings
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

M = TypeVar("M", bound=BaseModel)


class RabbitMQAcknowledger(MessageAcknowledger):
    """Wraps a single aio-pika IncomingMessage for ack/nack control.

    Workers call ack() on success, nack(requeue=False) to send to DLQ.
    Rule 19: Never requeue=True in code — that creates retry loops.
    """

    def __init__(self, incoming: aio_pika.abc.AbstractIncomingMessage) -> None:
        self._incoming = incoming

    async def ack(self) -> None:
        """Acknowledge successful processing — removes message from queue."""
        await self._incoming.ack()

    async def nack(self, requeue: bool = False) -> None:
        """Negative-acknowledge — routes to DLQ when requeue=False.

        Args:
            requeue: MUST remain False in production. Setting True creates
                     infinite retry loops. Rule 19: retries via RabbitMQ policy only.
        """
        await self._incoming.nack(requeue=requeue)


class RabbitMQConsumer(MessageConsumer):
    """Async iterator consumer for a single RabbitMQ queue.

    Deserializes incoming JSON messages into typed Pydantic models.
    One consumer instance per queue per worker process.

    Usage:
        consumer = await RabbitMQConsumer.create(url, QueueNames.STT, STTCompletedMessage)
        async for message, ack in consumer.consume(QueueNames.STT):
            # process message
            await ack.ack()
    """

    def __init__(
        self,
        connection: aio_pika.abc.AbstractRobustConnection,
        channel: aio_pika.abc.AbstractRobustChannel,
        queue: aio_pika.abc.AbstractQueue,
        schema: type[BaseModel],
    ) -> None:
        self._connection = connection
        self._channel = channel
        self._queue = queue
        self._schema = schema

    @classmethod
    async def create(
        cls,
        rabbitmq_url: str,
        queue_name: str,
        schema: type[BaseModel],
        prefetch_count: int | None = None,
    ) -> "RabbitMQConsumer":
        """Factory method — creates connection and binds to the named queue.

        Args:
            rabbitmq_url: AMQP URL.
            queue_name: Queue to consume from (must already be declared).
            schema: Pydantic model class to deserialize messages into.
            prefetch_count: Max unacknowledged messages. Defaults to settings value.

        Returns:
            Ready-to-consume RabbitMQConsumer instance.
        """
        settings = get_rabbitmq_settings()
        count = prefetch_count if prefetch_count is not None else settings.rabbitmq_prefetch_count

        connection = await aio_pika.connect_robust(rabbitmq_url)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=count)

        from src.infrastructure.messaging.queue_config import ExchangeNames

        # 1. Declare Main Exchange & DLX
        exchange = await channel.declare_exchange(
            ExchangeNames.MAIN, type=aio_pika.ExchangeType.DIRECT, durable=True
        )
        dlx = await channel.declare_exchange(
            ExchangeNames.DEAD_LETTER, type=aio_pika.ExchangeType.DIRECT, durable=True
        )

        # 2. Declare and Bind Dead-Letter Queue (DLQ)
        dlq_name = f"{queue_name}.dlq"
        dlq = await channel.declare_queue(dlq_name, durable=True)
        await dlq.bind(dlx, routing_key=queue_name)

        # 3. Declare and Bind Main Queue (routes to DLX on nack/failure)
        queue = await channel.declare_queue(
            queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": ExchangeNames.DEAD_LETTER,
                "x-dead-letter-routing-key": queue_name,
            },
        )
        await queue.bind(exchange, routing_key=queue_name)

        logger.info(
            "rabbitmq.consumer_ready",
            queue=queue_name,
            schema=schema.__name__,
            prefetch_count=count,
        )
        return cls(connection, channel, queue, schema)

    async def consume(  # type: ignore[override]
        self,
        queue_name: str,
    ) -> AsyncIterator[tuple[BaseModel, RabbitMQAcknowledger]]:
        """Async iterator that yields (typed_message, acknowledger) pairs.

        Args:
            queue_name: Ignored — this consumer is bound to a single queue at creation.
                        Present for interface compliance.

        Yields:
            Tuple of (deserialized Pydantic message, RabbitMQAcknowledger).

        Raises:
            MessagingError: On broker connection failure.
            MessageDeserializationError: Yields are skipped; malformed messages are nack'd.
        """
        async with self._queue.iterator() as queue_iter:
            async for incoming in queue_iter:
                async with incoming.process(ignore_processed=True):
                    ack = RabbitMQAcknowledger(incoming)
                    try:
                        body = incoming.body.decode("utf-8")
                        message = self._schema.model_validate_json(body)
                        yield message, ack
                    except ValidationError as exc:
                        logger.error(
                            "rabbitmq.deserialization_failed",
                            queue=self._queue.name,
                            schema=self._schema.__name__,
                            error=str(exc),
                            body_preview=incoming.body[:200].decode("utf-8", errors="replace"),
                        )
                        # Malformed messages go to DLQ — do not requeue
                        await ack.nack(requeue=False)
                        raise MessageDeserializationError(
                            f"Failed to deserialize message on queue "
                            f"'{self._queue.name}' into {self._schema.__name__}: {exc}"
                        ) from exc

    async def close(self) -> None:
        """Close channel and connection gracefully."""
        await self._channel.close()
        await self._connection.close()
        logger.info("rabbitmq.consumer_closed", queue=self._queue.name)
