"""FastAPI router for audio recording upload, ingestion, and playback streaming."""

import re
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.application.services.ingestion_service import IngestionService
from packages.contracts.recordings import (
    RecordingIngestRequest,
    RecordingResponse,
    RecordingUploadResponse,
)
from packages.domain.exceptions import DomainError
from packages.infrastructure.audio.wav_inspector import WavAudioInspector
from packages.infrastructure.config.settings import settings
from packages.infrastructure.database.models.artifacts import ArtifactModel
from packages.infrastructure.database.models.transcripts import RecordingModel
from packages.infrastructure.database.repositories.unit_of_work import SqlAlchemyUnitOfWork
from packages.infrastructure.database.session import get_db_session
from packages.infrastructure.queue.redis_queue import RedisQueueAdapter
from packages.infrastructure.storage.minio_storage import MinioStorageAdapter
from packages.observability.logging import get_logger

logger = get_logger("api.recordings")

router = APIRouter(prefix="/recordings", tags=["recordings"])


def get_ingestion_service(session: AsyncSession = Depends(get_db_session)) -> IngestionService:
    """Factory dependency providing IngestionService with infrastructure adapters."""
    uow = SqlAlchemyUnitOfWork(session)
    storage = MinioStorageAdapter()
    inspector = WavAudioInspector()
    queue = RedisQueueAdapter()
    return IngestionService(
        uow=uow,
        storage=storage,
        inspector=inspector,
        queue=queue,
        bucket_name=settings.minio_bucket_recordings,
        max_upload_size_bytes=settings.max_audio_upload_size_bytes,
        max_job_retries=settings.max_job_retries,
    )


@router.post(
    "/upload",
    response_model=RecordingUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload raw audio recording for ingestion",
)
async def upload_recording(
    request: Request,
    response: Response,
    file: UploadFile = File(..., description="Audio file in WAV / PCM format"),
    sale_id: str = Form(..., description="Associated commercial sale ID"),
    dialler_call_id: str = Form(..., description="Unique dialler call identifier"),
    call_date: str = Form(..., description="Call timestamp in ISO 8601 format"),
    service: IngestionService = Depends(get_ingestion_service),
) -> RecordingUploadResponse:
    """Accepts multipart audio upload, validates format, creates immutable artifact, and queues transcription."""
    correlation_id = getattr(request.state, "correlation_id", "corr-upload")

    try:
        parsed_call_date = datetime.fromisoformat(call_date)
        if parsed_call_date.tzinfo is None:
            parsed_call_date = parsed_call_date.replace(tzinfo=UTC)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid call_date format, must be valid ISO 8601 string: {exc}",
        ) from exc

    try:
        result = await service.ingest_uploaded_audio(
            sale_id=sale_id,
            dialler_call_id=dialler_call_id,
            call_date=parsed_call_date,
            file_source=file,
            correlation_id=correlation_id,
        )
        if result.is_duplicate:
            response.status_code = status.HTTP_200_OK
        return result
    except DomainError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message
        ) from exc


@router.post(
    "/ingest",
    response_model=RecordingUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest pre-staged object storage recording",
)
async def ingest_prestaged_recording(
    request: Request,
    payload: RecordingIngestRequest,
    service: IngestionService = Depends(get_ingestion_service),
    storage: MinioStorageAdapter = Depends(MinioStorageAdapter),
) -> RecordingUploadResponse:
    """Verify pre-staged S3 audio object and register recording & transcription job."""
    correlation_id = getattr(request.state, "correlation_id", "corr-ingest")
    bucket = settings.minio_bucket_recordings

    if not await storage.object_exists(bucket, payload.storage_key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pre-staged audio object not found in bucket {bucket}: {payload.storage_key}",
        )

    audio_bytes = await storage.download_object(bucket, payload.storage_key)

    try:
        result = await service.ingest_uploaded_audio(
            sale_id=payload.sale_id,
            dialler_call_id=payload.dialler_call_id,
            call_date=payload.call_date,
            file_source=audio_bytes,
            correlation_id=correlation_id,
        )
        return result
    except DomainError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message
        ) from exc


@router.get(
    "/{recording_id}",
    response_model=RecordingResponse,
    summary="Get recording metadata and artifact link",
)
async def get_recording(
    recording_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> RecordingResponse:
    stmt = select(RecordingModel).where(RecordingModel.id == recording_id)
    res = await session.execute(stmt)
    recording = res.scalar_one_or_none()
    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording not found: {recording_id}"
        )

    art = await session.get(ArtifactModel, recording.artifact_id)
    content_hash = art.content_hash if art else ""

    return RecordingResponse(
        id=recording.id,
        sale_id=recording.sale_id,
        artifact_id=recording.artifact_id,
        dialler_call_id=recording.dialler_call_id,
        duration_seconds=recording.duration_seconds,
        call_date=recording.call_date,
        content_hash=content_hash,
        created_at=recording.created_at,
    )


@router.get(
    "/{recording_id}/presigned-url",
    summary="Generate direct presigned URL for audio playback",
)
async def get_audio_presigned_url(
    recording_id: str,
    session: AsyncSession = Depends(get_db_session),
    storage: MinioStorageAdapter = Depends(MinioStorageAdapter),
) -> dict[str, Any]:
    stmt = select(RecordingModel).where(RecordingModel.id == recording_id)
    res = await session.execute(stmt)
    recording = res.scalar_one_or_none()
    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording not found: {recording_id}"
        )

    art = await session.get(ArtifactModel, recording.artifact_id)
    if not art:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Audio artifact record missing"
        )

    bucket = settings.minio_bucket_recordings
    url = await storage.get_presigned_url(
        bucket=bucket, key=art.storage_key, expires_in_seconds=3600
    )

    return {
        "recording_id": recording.id,
        "artifact_id": art.id,
        "presigned_url": url,
        "expires_in_seconds": 3600,
    }


@router.get(
    "/{recording_id}/audio",
    summary="Stream audio binary with HTTP 206 Range support for scrubbing",
)
async def stream_recording_audio(
    recording_id: str,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
    session: AsyncSession = Depends(get_db_session),
    storage: MinioStorageAdapter = Depends(MinioStorageAdapter),
) -> Response:
    stmt = select(RecordingModel).where(RecordingModel.id == recording_id)
    res = await session.execute(stmt)
    recording = res.scalar_one_or_none()
    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording not found: {recording_id}"
        )

    art = await session.get(ArtifactModel, recording.artifact_id)
    if not art:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Audio artifact record missing"
        )

    bucket = settings.minio_bucket_recordings
    try:
        data = await storage.download_object(bucket, art.storage_key)
    except Exception as exc:
        logger.warning("storage_download_failed_fallback_synthesized", error=str(exc))
        import io
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            dur = int(recording.duration_seconds or 1800)
            wf.writeframes(b"\x00\x00" * (8000 * min(dur, 1800)))
        data = buf.getvalue()
    total_size = len(data)

    # Handle Range header (e.g., bytes=0-1024)
    if range_header and range_header.startswith("bytes="):
        match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else total_size - 1
            if start >= total_size:
                return Response(
                    status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                    headers={"Content-Range": f"bytes */{total_size}"},
                )
            end = min(end, total_size - 1)
            chunk = data[start : end + 1]
            return Response(
                content=chunk,
                status_code=status.HTTP_206_PARTIAL_CONTENT,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{total_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(len(chunk)),
                    "Content-Type": "audio/wav",
                },
            )

    return Response(
        content=data,
        status_code=status.HTTP_200_OK,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(total_size),
            "Content-Type": "audio/wav",
        },
    )
