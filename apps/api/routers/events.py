"""FastAPI router for real-time Server-Sent Events (SSE) notification streaming."""

import asyncio
import json
from datetime import UTC, datetime
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from apps.api.dependencies import get_current_principal
from packages.contracts.events import RealtimeNotification
from packages.contracts.security import Principal
from packages.infrastructure.config.settings import settings
from packages.observability.logging import get_logger

logger = get_logger("api.events")

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get(
    "/stream",
    summary="Subscribe to tenant-specific real-time evaluation and outbox events via SSE",
)
async def event_stream(
    request: Request,
    tenant_id: str | None = Query(None, description="Optional tenant ID override for browser EventSource"),
    single_event_only: bool = Query(False, include_in_schema=False),
    principal: Principal = Depends(get_current_principal),
) -> StreamingResponse:
    """Streams Server-Sent Events (SSE) for real-time UI refresh.

    Lightweight notification pointers: clients refetch authoritative state upon receipt.
    """
    effective_tenant = tenant_id or principal.tenant_id

    async def _event_generator() -> AsyncGenerator[str, None]:
        # Initial connection acknowledgement
        initial_event = {
            "event_id": "init",
            "event_type": "Connected",
            "tenant_id": effective_tenant,
            "occurred_at": datetime.now(UTC).isoformat(),
        }
        yield f"event: Connected\ndata: {json.dumps(initial_event)}\n\n"

        if single_event_only:
            return

        # Try to connect to Redis Pub/Sub if configured and not in test environment
        redis_client = None
        pubsub = None
        if settings.app_env.lower() not in {"test", "testing"}:
            try:
                import redis.asyncio as aioredis
                redis_client = aioredis.from_url(
                    settings.redis_url, decode_responses=True, socket_connect_timeout=0.5, socket_timeout=0.5
                )
                pubsub = redis_client.pubsub()
                channel = f"tenant:{effective_tenant}:events"
                await asyncio.wait_for(pubsub.subscribe(channel), timeout=0.5)
                logger.info("sse_subscribed_to_redis", tenant_id=effective_tenant, channel=channel)
            except Exception as exc:
                logger.warning("sse_redis_unavailable_fallback_to_heartbeat", error=str(exc))
                pubsub = None
                if redis_client:
                    try:
                        await redis_client.close()
                    except Exception:
                        pass
                    redis_client = None

        try:
            while True:
                if pubsub:
                    try:
                        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                        if message and message.get("type") == "message":
                            raw_data = message.get("data", "{}")
                            parsed = json.loads(raw_data)
                            event_type = parsed.get("event_type", "Notification")
                            yield f"event: {event_type}\ndata: {raw_data}\n\n"
                    except Exception as exc:
                        logger.warning("sse_pubsub_read_error", error=str(exc))

                # Periodic keep-alive ping comment
                yield ": ping\n\n"
                await asyncio.sleep(2.0)

        except asyncio.CancelledError:
            logger.info("sse_client_disconnected", tenant_id=effective_tenant)
        finally:
            if pubsub:
                try:
                    await pubsub.unsubscribe()
                    await pubsub.close()
                except Exception:
                    pass
            if redis_client:
                try:
                    await redis_client.close()
                except Exception:
                    pass

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
