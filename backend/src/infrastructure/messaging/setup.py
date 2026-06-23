"""RabbitMQ exchange and queue topology setup.

Call once at application/worker startup to declare all exchanges and queues.
Uses the DLX (dead-letter exchange) pattern:
  - Every processing queue has x-dead-letter-exchange configured
  - Failed messages (nack with requeue=False) route to the DLQ automatically

Queue topology:
    Exchange: audio_analysis.main (direct)
    Exchange: audio_analysis.dlx  (dead-letter, direct)

    ingestion_queue         -> on failure -> ingestion_queue.dlq
    stt_queue               -> on failure -> stt_queue.dlq
    transcript_repair_queue -> on failure -> transcript_repair_queue.dlq
    behavioral_analysis_queue -> on failure -> behavioral_analysis_queue.dlq
    report_queue            -> on failure -> report_queue.dlq
"""

import aio_pika
from aio_pika.abc import AbstractRobustChannel

from src.infrastructure.logging.logger import get_logger
from src.infrastructure.messaging.queue_config import ExchangeNames, QueueNames

logger = get_logger(__name__)

# All processing queues that need DLQ binding
_PROCESSING_QUEUES: list[str] = [
    QueueNames.INGESTION,
    QueueNames.STT,
    QueueNames.TRANSCRIPT_REPAIR,
    QueueNames.BEHAVIORAL_ANALYSIS,
    QueueNames.REPORT,
]

_DLQ_MAP: dict[str, str] = {
    QueueNames.INGESTION: QueueNames.INGESTION_DLQ,
    QueueNames.STT: QueueNames.STT_DLQ,
    QueueNames.TRANSCRIPT_REPAIR: QueueNames.TRANSCRIPT_REPAIR_DLQ,
    QueueNames.BEHAVIORAL_ANALYSIS: QueueNames.BEHAVIORAL_ANALYSIS_DLQ,
    QueueNames.REPORT: QueueNames.REPORT_DLQ,
}


async def declare_topology(channel: AbstractRobustChannel) -> None:
    """Declare all exchanges and queues idempotently.

    Safe to call multiple times — uses durable declarations that no-op if
    the exchange/queue already exists with identical arguments.

    Args:
        channel: An open aio-pika channel (robust connection recommended).
    """
    # 1. Declare main exchange
    main_exchange = await channel.declare_exchange(
        ExchangeNames.MAIN,
        aio_pika.ExchangeType.DIRECT,
        durable=True,
    )

    # 2. Declare dead-letter exchange
    dlx_exchange = await channel.declare_exchange(
        ExchangeNames.DEAD_LETTER,
        aio_pika.ExchangeType.DIRECT,
        durable=True,
    )

    # 3. Declare DLQs first (main queues reference them)
    for queue_name, dlq_name in _DLQ_MAP.items():
        dlq = await channel.declare_queue(
            dlq_name,
            durable=True,
            arguments={},
        )
        await dlq.bind(dlx_exchange, routing_key=queue_name)
        logger.info("rabbitmq.dlq_declared", queue=dlq_name)

    # 4. Declare main processing queues with DLX binding
    for queue_name in _PROCESSING_QUEUES:
        queue = await channel.declare_queue(
            queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": ExchangeNames.DEAD_LETTER,
                "x-dead-letter-routing-key": queue_name,
            },
        )
        await queue.bind(main_exchange, routing_key=queue_name)
        logger.info("rabbitmq.queue_declared", queue=queue_name)

    logger.info(
        "rabbitmq.topology_ready",
        exchange=ExchangeNames.MAIN,
        dlx=ExchangeNames.DEAD_LETTER,
        queue_count=len(_PROCESSING_QUEUES),
    )
