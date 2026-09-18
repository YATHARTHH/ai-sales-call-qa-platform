"""Operational health, readiness, and metrics endpoints."""

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import get_queue, get_storage
from packages.application.ports.queue import QueuePort
from packages.application.ports.storage import StoragePort
from packages.contracts.health import HealthResponse, ReadinessResponse
from packages.infrastructure.database.session import get_db_session
from packages.observability.metrics import generate_latest

router = APIRouter(tags=["Operational"])


@router.get("/health", response_model=HealthResponse, summary="Liveness Probe")
async def liveness_check() -> HealthResponse:
    """Liveness probe confirming the web process is running.

    Does NOT depend on external infrastructure to prevent cascading container restarts.
    """
    return HealthResponse(status="ok")


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness Probe",
    responses={503: {"model": ReadinessResponse}},
)
async def readiness_check(
    db: AsyncSession = Depends(get_db_session),
    storage: StoragePort = Depends(get_storage),
    queue: QueuePort = Depends(get_queue),
):
    """Readiness probe checking PostgreSQL, Redis, and MinIO connectivity."""
    dependencies: dict[str, str] = {}
    is_ready = True

    # 1. Probe PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        dependencies["postgres"] = "ok"
    except Exception as e:
        dependencies["postgres"] = f"unhealthy: {type(e).__name__}"
        is_ready = False

    # 2. Probe Redis
    try:
        redis_ok = await queue.check_connection()
        dependencies["redis"] = "ok" if redis_ok else "unhealthy"
        if not redis_ok:
            is_ready = False
    except Exception as e:
        dependencies["redis"] = f"unhealthy: {type(e).__name__}"
        is_ready = False

    # 3. Probe MinIO
    try:
        minio_ok = await storage.check_connection()
        dependencies["minio"] = "ok" if minio_ok else "unhealthy"
        if not minio_ok:
            is_ready = False
    except Exception as e:
        dependencies["minio"] = f"unhealthy: {type(e).__name__}"
        is_ready = False

    payload = ReadinessResponse(
        status="ready" if is_ready else "not_ready",
        dependencies=dependencies,
    )

    if not is_ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload.model_dump(),
        )
    return payload


@router.get("/metrics", summary="Prometheus Metrics Exporter")
async def metrics_endpoint():
    """Export Prometheus metrics in standard text format."""
    return PlainTextResponse(generate_latest())
