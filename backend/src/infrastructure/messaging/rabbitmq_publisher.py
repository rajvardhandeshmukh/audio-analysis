"""RabbitMQ publisher — implements MessagePublisher port.

Rule 6: This is the ONLY place that calls aio-pika publish methods.
Services and workers call this via the MessagePublisher ABC only.
"""

import json

import aio_pika
from pydantic import BaseModel

from src.domain.errors.domain_errors import MessagePublishError
from src.domain.ports.storage_messaging import MessagePublisher
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.messaging.queue_config import ExchangeNames

logger = get_logger(__name__)


class RabbitMQPublisher(MessagePublisher):
    """Publishes typed Pydantic messages to RabbitMQ via the main exchange.

    Serializes messages to JSON. Uses persistent delivery mode (survives broker restart).
    All messages are routed by queue name as routing key on the direct exchange.

    Usage:
        publisher = await RabbitMQPublisher.create(rabbitmq_url)
        await publisher.publish(QueueNames.INGESTION, IngestionMessage(...))
    """

    def __init__(
        self,
        connection: aio_pika.abc.AbstractRobustConnection,
        channel: aio_pika.abc.AbstractRobustChannel,
        exchange: aio_pika.abc.AbstractExchange,
    ) -> None:
        self._connection = connection
        self._channel = channel
        self._exchange = exchange

    @classmethod
    async def create(cls, rabbitmq_url: str) -> "RabbitMQPublisher":
        """Factory method — creates connection, channel, and exchange reference.

        Args:
            rabbitmq_url: AMQP URL e.g. amqp://user:pass@localhost:5672/

        Returns:
            Ready-to-use RabbitMQPublisher instance.

        Raises:
            MessagingError: On connection failure.
        """
        connection = await aio_pika.connect_robust(rabbitmq_url)
        channel = await connection.channel()
        # Ensure the exchange exists before publishing
        exchange = await channel.declare_exchange(
            ExchangeNames.MAIN, type=aio_pika.ExchangeType.DIRECT, durable=True
        )
        logger.info("rabbitmq.publisher_connected", url=rabbitmq_url.split("@")[-1])
        return cls(connection, channel, exchange)

    async def publish(
        self,
        queue_name: str,
        message: BaseModel,
        priority: int = 0,
    ) -> None:
        """Publish a typed message to the named queue.

        Args:
            queue_name: Routing key / target queue name.
            message: Typed Pydantic message (never raw dict).
            priority: Message priority 0-10. Requires priority queue config.

        Raises:
            MessagePublishError: On serialization or broker send failure.
        """
        try:
            body = message.model_dump_json().encode("utf-8")
            amqp_message = aio_pika.Message(
                body=body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json",
                priority=priority,
            )
            await self._exchange.publish(amqp_message, routing_key=queue_name)
            logger.info(
                "rabbitmq.message_published",
                queue=queue_name,
                message_type=type(message).__name__,
                body_bytes=len(body),
            )
        except Exception as exc:
            raise MessagePublishError(
                f"Failed to publish {type(message).__name__} to '{queue_name}': {exc}"
            ) from exc

    async def close(self) -> None:
        """Close channel and connection gracefully."""
        await self._channel.close()
        await self._connection.close()
        logger.info("rabbitmq.publisher_closed")
