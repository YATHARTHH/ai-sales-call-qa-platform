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


from fastapi import WebSocket, WebSocketDisconnect

@router.websocket("/ws/stream/{call_id}")
async def websocket_stream_monitor(websocket: WebSocket, call_id: str) -> None:
    """Live WebSocket audio stream monitoring & real-time incremental compliance checking.

    Clients send JSON frame objects containing transcript chunks or audio metadata:
        {"speaker": "AGENT", "text": "This call is being recorded for quality..."}

    Server evaluates compliance in real-time and pushes back immediate breach alerts.
    """
    await websocket.accept()
    logger.info("websocket_stream_connected", call_id=call_id)

    transcript_buffer = []
    
    try:
        # Initial ack
        await websocket.send_json({
            "type": "CONNECTION_ACK",
            "call_id": call_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "STREAMING_READY"
        })

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "TRANSCRIPT_CHUNK")

            if msg_type == "PING":
                await websocket.send_json({"type": "PONG", "timestamp": datetime.now(UTC).isoformat()})
                continue

            if msg_type == "TRANSCRIPT_CHUNK":
                speaker = data.get("speaker", "AGENT")
                text = data.get("text", "")
                timestamp_ms = data.get("timestamp_ms", 0)

                transcript_buffer.append({"speaker": speaker, "text": text, "timestamp_ms": timestamp_ms})
                full_text = " ".join([t["text"] for t in transcript_buffer]).lower()

                # Live compliance checks
                recording_disclosed = "recorded" in full_text or "quality" in full_text
                eic_detected = "explicit" in full_text or "consent" in full_text or "agree" in full_text

                await websocket.send_json({
                    "type": "INCREMENTAL_EVALUATION",
                    "call_id": call_id,
                    "chunks_received": len(transcript_buffer),
                    "live_checks": {
                        "recording_disclosure": "PASS" if recording_disclosed else "PENDING",
                        "explicit_informed_consent": "PASS" if eic_detected else "PENDING",
                    },
                    "timestamp": datetime.now(UTC).isoformat()
                })

            elif msg_type == "STREAM_END":
                await websocket.send_json({
                    "type": "STREAM_COMPLETED",
                    "call_id": call_id,
                    "total_chunks": len(transcript_buffer),
                    "final_status": "QUEUED_FOR_FULL_AUDIT"
                })
                break

    except WebSocketDisconnect:
        logger.info("websocket_stream_disconnected", call_id=call_id)
    except Exception as exc:
        logger.error("websocket_stream_error", call_id=call_id, error=str(exc))
        try:
            await websocket.send_json({"type": "ERROR", "message": str(exc)})
        except Exception:
            pass
