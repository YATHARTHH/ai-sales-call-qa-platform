"""FastAPI Application Entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.middleware import CorrelationAndMetricsMiddleware
from apps.api.routers.analytics import router as analytics_router
from apps.api.routers.evaluations import router as evaluations_router
from apps.api.routers.events import router as events_router
from apps.api.routers.health import router as health_router
from apps.api.routers.recordings import router as recordings_router
from apps.api.routers.transcripts import router as transcripts_router
from packages.contracts.errors import ErrorDetail, ErrorResponse
from packages.domain.exceptions import DomainError
from packages.infrastructure.config.settings import settings
from packages.observability.logging import configure_logging, get_logger

logger = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifespan context."""
    configure_logging(log_level=settings.log_level, json_format=(settings.log_format == "json"))
    logger.info("application_startup", app=settings.app_name, env=settings.app_env)
    yield
    logger.info("application_shutdown", app=settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description="Evidence-Driven AI Sales QA & Compliance Automation Platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(CorrelationAndMetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global Domain Exception Handler
@app.exception_handler(DomainError)
async def domain_exception_handler(request: Request, exc: DomainError):
    request_id = getattr(request.state, "request_id", None)
    logger.warning("domain_error", error_code=exc.code, message=exc.message)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ErrorResponse(
            error=ErrorDetail(
                code=exc.code,
                message=exc.message,
                request_id=request_id,
            )
        ).model_dump(),
    )


# Global Generic Exception Handler
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.error("internal_server_error", error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error=ErrorDetail(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected server error occurred.",
                request_id=request_id,
            )
        ).model_dump(),
    )


# Mount routers
app.include_router(health_router)
app.include_router(recordings_router, prefix="/api/v1")
app.include_router(transcripts_router, prefix="/api/v1")
app.include_router(evaluations_router)
app.include_router(analytics_router)
app.include_router(events_router)


from datetime import UTC, datetime
from fastapi import WebSocket, WebSocketDisconnect


async def _ws_handler(websocket: WebSocket, call_id: str) -> None:
    """Shared WebSocket handler — reused across both registered paths."""
    await websocket.accept()
    logger.info("websocket_stream_connected", call_id=call_id)

    transcript_buffer = []

    try:
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


# Register both canonical paths separately — stacking @app.websocket is NOT supported
@app.websocket("/api/v1/events/ws/stream/{call_id}")
async def ws_stream_v1(websocket: WebSocket, call_id: str) -> None:
    await _ws_handler(websocket, call_id)


@app.websocket("/ws/stream/{call_id}")
async def ws_stream_root(websocket: WebSocket, call_id: str) -> None:
    await _ws_handler(websocket, call_id)
