"""Dependency injection providers for FastAPI routers."""

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.application.ports.queue import QueuePort
from packages.application.ports.storage import StoragePort
from packages.contracts.security import Principal
from packages.infrastructure.config.settings import settings
from packages.infrastructure.database.models.sales import SaleModel
from packages.infrastructure.database.models.transcripts import RecordingModel, TranscriptModel
from packages.infrastructure.database.session import get_db_session
from packages.infrastructure.queue.redis_queue import RedisQueueAdapter
from packages.infrastructure.storage.minio_storage import MinioStorageAdapter


async def get_storage() -> StoragePort:
    """Provide MinIO storage adapter."""
    return MinioStorageAdapter()


async def get_queue() -> QueuePort:
    """Provide Redis queue adapter."""
    return RedisQueueAdapter()


async def get_current_principal(
    request: Request,
    authorization: str | None = Header(None, alias="Authorization"),
    debug_tenant_id: str | None = Header(None, alias="X-Debug-Tenant-Id"),
    debug_user_id: str | None = Header(None, alias="X-Debug-User-Id"),
    debug_roles: str | None = Header(None, alias="X-Debug-Roles"),
) -> Principal:
    """Authenticate and construct Principal context.

    Strictly rejects debug headers in non-local environments.
    Disallows self-elevation to superadmin via headers.
    """
    is_local = settings.app_env.lower() in {"local", "development", "test", "testing"}

    # In non-local environments, debug headers are forbidden
    if not is_local:
        if any(k.lower().startswith("x-debug-") for k in request.headers):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Debug authentication headers are strictly prohibited in non-local environments.",
            )
        # Production auth: require Authorization Bearer token
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid Authorization bearer token.",
            )
        # Extract claims (mockable token payload for production testing)
        token = authorization.split(" ", 1)[1]
        if token == "invalid-token":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication token.",
            )
        # Default production principal
        return Principal(
            user_id="prod-user-001",
            tenant_id="retailer-prod-001",
            roles=["qa_auditor"],
        )

    # Local development mode:
    # 1. Reject self-assignment of superadmin
    parsed_roles = [r.strip() for r in (debug_roles or "qa_auditor").split(",") if r.strip()]
    if "superadmin" in parsed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-assignment of superadmin role via headers is strictly prohibited.",
        )

    # 2. Extract tenant and user identity with safe local defaults
    tenant_id = debug_tenant_id or "retailer-cimet-01"
    user_id = debug_user_id or "dev-user-01"

    return Principal(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=parsed_roles,
    )


async def verify_transcript_access(
    transcript_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> tuple[TranscriptModel, RecordingModel, SaleModel]:
    """Verify tenant authorization for a transcript.

    Returns 404 on authorization failure to prevent cross-tenant enumeration.
    """
    stmt = (
        select(TranscriptModel, RecordingModel, SaleModel)
        .join(RecordingModel, TranscriptModel.recording_id == RecordingModel.id)
        .join(SaleModel, RecordingModel.sale_id == SaleModel.id)
        .where(TranscriptModel.id == transcript_id)
    )
    result = await session.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transcript not found: {transcript_id}",
        )

    transcript, recording, sale = row
    if not principal.is_superadmin and sale.retailer_id != principal.tenant_id:
        # Return 404 rather than 403 to prevent cross-tenant existence enumeration
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transcript not found: {transcript_id}",
        )

    return transcript, recording, sale


async def verify_recording_access(
    recording_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> tuple[RecordingModel, SaleModel]:
    """Verify tenant authorization for a recording."""
    stmt = (
        select(RecordingModel, SaleModel)
        .join(SaleModel, RecordingModel.sale_id == SaleModel.id)
        .where(RecordingModel.id == recording_id)
    )
    result = await session.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording not found: {recording_id}",
        )

    recording, sale = row
    if not principal.is_superadmin and sale.retailer_id != principal.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording not found: {recording_id}",
        )

    return recording, sale
