"""Redis pub/sub event publisher — publishes JobProgressEvent to WebSocket consumers.

Workers call publish_progress() after each pipeline stage.
The WebSocket server subscribes to the job_events channel and pushes to connected clients.
"""

import json

from src.infrastructure.cache.redis_client import get_redis
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.messaging.queue_config import RedisChannels
from src.infrastructure.messaging.schemas import JobProgressEvent

logger = get_logger(__name__)


async def publish_progress(event: JobProgressEvent) -> None:
    """Publish a job progress event to Redis pub/sub.

    Args:
        event: Typed progress event. Serialized to JSON before publishing.
    """
    redis = get_redis()
    try:
        payload = event.model_dump_json()
        await redis.publish(RedisChannels.JOB_EVENTS, payload)
        logger.info(
            "redis.event_published",
            job_id=str(event.job_id),
            status=event.status,
            stage=event.stage,
        )
    except Exception as exc:
        # Progress events are best-effort — do not fail the worker on publish errors
        logger.warning(
            "redis.event_publish_failed",
            job_id=str(event.job_id),
            error=str(exc),
        )
    finally:
        await redis.aclose()
