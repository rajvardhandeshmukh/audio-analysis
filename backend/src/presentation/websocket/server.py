"""WebSocket server — pushes job progress events to connected clients.

Protocol:
  Client connects: ws://host/ws/jobs/{job_id}
  Server pushes:   JSON { job_id, status, stage, message, timestamp }
  on every Redis pub/sub event for that job.

Auth: Bearer token passed as query param `?token=<jwt>` (WS doesn't support headers).
"""

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from src.domain.errors.domain_errors import AuthenticationError
from src.infrastructure.auth.jwt_service import JWTService
from src.infrastructure.cache.redis_client import get_redis
from src.infrastructure.config.settings import get_auth_settings
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.messaging.queue_config import RedisChannels

logger = get_logger(__name__)

ws_router = APIRouter(tags=["WebSocket"])


def _get_jwt() -> JWTService:
    cfg = get_auth_settings()
    return JWTService(cfg.jwt_secret_key, cfg.jwt_algorithm, cfg.jwt_expire_minutes)


@ws_router.websocket("/ws/jobs/{job_id}")
async def job_progress_ws(
    websocket: WebSocket,
    job_id: UUID,
    token: str = Query(..., description="JWT bearer token"),
) -> None:
    """Stream real-time job progress events.

    Authenticates via `?token=<jwt>` query parameter (WS limitation).
    Delivers all Redis pub/sub events matching the requested job_id.
    Closes with code 1008 on auth failure.
    """
    jwt_service = _get_jwt()
    try:
        jwt_service.decode_token(token)
    except AuthenticationError as exc:
        await websocket.close(code=1008, reason=exc.message)
        return

    await websocket.accept()
    logger.info("ws.connected", job_id=str(job_id))

    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(RedisChannels.JOB_EVENTS)

    try:
        async for raw in pubsub.listen():
            if websocket.client_state != WebSocketState.CONNECTED:
                break
            if raw["type"] != "message":
                continue
            try:
                data = json.loads(raw["data"])
            except (json.JSONDecodeError, TypeError):
                continue

            # Only forward events for the requested job
            if str(data.get("job_id")) != str(job_id):
                continue

            await websocket.send_json(data)

            # Disconnect client on terminal states
            if data.get("status") in ("completed", "failed"):
                break
    except WebSocketDisconnect:
        logger.info("ws.client_disconnected", job_id=str(job_id))
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe(RedisChannels.JOB_EVENTS)
        await pubsub.aclose()
        await redis.aclose()
        logger.info("ws.closed", job_id=str(job_id))
