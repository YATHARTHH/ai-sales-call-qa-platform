"""Application service orchestrating audio recording ingestion, deduplication, and storage."""

import asyncio
import hashlib
import os
import tempfile
import uuid
from datetime import UTC, datetime
from typing import Any

from packages.application.ports.audio import AudioInspectorPort, AudioMetadata
from packages.application.ports.queue import QueuePort
from packages.application.ports.repositories import UnitOfWorkPort
from packages.application.ports.storage import StoragePort
from packages.contracts.recordings import RecordingUploadResponse
from packages.domain.artifacts import Artifact
from packages.domain.audit import ActorType, AuditEvent
from packages.domain.exceptions import DomainError
from packages.domain.jobs import JobStatus, PipelineJob
from packages.domain.retail import Sale
from packages.domain.transcript import Recording
from packages.observability.logging import get_logger
from packages.observability.metrics import (
    RECORDING_AUDIO_DURATION_SECONDS,
    RECORDING_FILE_SIZE_BYTES,
    RECORDING_INGESTION_DURATION_SECONDS,
    RECORDING_INGESTION_TOTAL,
)

logger = get_logger("service.ingestion")

DEFAULT_PROCESSOR_VERSION = "whisper-large-v3@2026.1+pyannote@3.1"


class IngestionService:
    """Orchestrates bounded-memory audio ingestion, race-safe deduplication, and durable job dispatch."""

    def __init__(
        self,
        uow: UnitOfWorkPort,
        storage: StoragePort,
        inspector: AudioInspectorPort,
        queue: QueuePort | None = None,
        bucket_name: str = "recordings",
        max_upload_size_bytes: int = 524_288_000,
        max_job_retries: int = 3,
        processor_version: str = DEFAULT_PROCESSOR_VERSION,
    ):
        self.uow = uow
        self.storage = storage
        self.inspector = inspector
        self.queue = queue
        self.bucket_name = bucket_name
        self.max_upload_size_bytes = max_upload_size_bytes
        self.max_job_retries = max_job_retries
        self.processor_version = processor_version

    async def ingest_uploaded_audio(
        self,
        sale_id: str,
        dialler_call_id: str,
        call_date: datetime,
        file_source: Any,
        correlation_id: str,
    ) -> RecordingUploadResponse:
        """Process raw audio stream via bounded chunking into MinIO and PostgreSQL."""
        start_time = datetime.now(UTC)
        logger.info(
            "recording_upload_started",
            sale_id=sale_id,
            dialler_call_id=dialler_call_id,
            correlation_id=correlation_id,
        )

        sale = await self._verify_sale_exists(sale_id)

        existing_duplicate = await self._check_dialler_call_id(dialler_call_id, correlation_id)
        if existing_duplicate:
            return existing_duplicate

        content_hash, total_bytes, audio_meta, temp_path = await self._buffer_and_inspect_audio(
            file_source, correlation_id
        )

        try:
            artifact, is_content_dup = await self._resolve_artifact(
                content_hash=content_hash,
                total_bytes=total_bytes,
                audio_meta=audio_meta,
                lead_id=sale.lead_id,
                temp_path=temp_path,
                correlation_id=correlation_id,
            )

            recording, is_rec_new = await self._save_recording(
                sale_id=sale_id,
                artifact_id=artifact.id,
                dialler_call_id=dialler_call_id,
                duration_seconds=audio_meta.duration_seconds,
                call_date=call_date,
            )
            if not is_rec_new:
                return RecordingUploadResponse(
                    recording_id=recording.id,
                    artifact_id=recording.artifact_id,
                    sale_id=recording.sale_id,
                    dialler_call_id=recording.dialler_call_id,
                    content_hash=content_hash,
                    duration_seconds=recording.duration_seconds,
                    is_duplicate=True,
                )

            job, is_new_job = await self._resolve_transcription_job(
                content_hash=content_hash,
                recording_id=recording.id,
                correlation_id=correlation_id,
            )

            await self._record_audit_event(
                recording_id=recording.id,
                artifact_id=artifact.id,
                content_hash=content_hash,
                duration_seconds=audio_meta.duration_seconds,
                is_content_duplicate=is_content_dup,
                job_id=job.id,
                correlation_id=correlation_id,
            )
            await self.uow.commit()

            if self.queue and is_new_job:
                await self._dispatch_to_queue(job.id, recording.id, artifact.id, correlation_id)

            self._record_metrics(start_time, audio_meta.duration_seconds, total_bytes)

            logger.info(
                "recording_ingestion_completed",
                recording_id=recording.id,
                artifact_id=artifact.id,
                job_id=job.id,
                correlation_id=correlation_id,
            )

            return RecordingUploadResponse(
                recording_id=recording.id,
                artifact_id=artifact.id,
                sale_id=sale_id,
                dialler_call_id=dialler_call_id,
                content_hash=content_hash,
                duration_seconds=audio_meta.duration_seconds,
                is_duplicate=False,
                job_id=job.id,
            )
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    async def _verify_sale_exists(self, sale_id: str) -> Sale:
        sale = await self.uow.sales.get_sale(sale_id)
        if not sale:
            RECORDING_INGESTION_TOTAL.labels(status="failure").inc()
            raise DomainError(f"Sale not found: {sale_id}", code="SALE_NOT_FOUND")
        return sale

    async def _check_dialler_call_id(
        self, dialler_call_id: str, correlation_id: str
    ) -> RecordingUploadResponse | None:
        existing_rec = await self.uow.transcripts.get_recording_by_dialler_id(dialler_call_id)
        if not existing_rec:
            return None

        logger.info(
            "dialler_call_id_duplicate_detected",
            dialler_call_id=dialler_call_id,
            existing_recording_id=existing_rec.id,
            correlation_id=correlation_id,
        )
        RECORDING_INGESTION_TOTAL.labels(status="duplicate_call").inc()
        art = await self.uow.artifacts.get_by_id(existing_rec.artifact_id)
        return RecordingUploadResponse(
            recording_id=existing_rec.id,
            artifact_id=existing_rec.artifact_id,
            sale_id=existing_rec.sale_id,
            dialler_call_id=existing_rec.dialler_call_id,
            content_hash=art.content_hash if art else "",
            duration_seconds=existing_rec.duration_seconds,
            is_duplicate=True,
        )

    async def _buffer_and_inspect_audio(
        self, file_source: Any, correlation_id: str
    ) -> tuple[str, int, AudioMetadata, str]:
        hasher = hashlib.sha256()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            temp_path = temp_file.name

        try:
            with open(temp_path, "wb") as f_out:
                total_bytes = await self._stream_to_file(file_source, f_out, hasher)

            if total_bytes == 0:
                RECORDING_INGESTION_TOTAL.labels(status="failure").inc()
                raise DomainError("Uploaded audio file is empty (0 bytes)", code="EMPTY_AUDIO_FILE")

            if total_bytes > self.max_upload_size_bytes:
                RECORDING_INGESTION_TOTAL.labels(status="failure").inc()
                raise DomainError(
                    f"Audio file size ({total_bytes} bytes) exceeds maximum limit ({self.max_upload_size_bytes} bytes)",
                    code="FILE_TOO_LARGE",
                )

            content_hash = hasher.hexdigest()
            audio_meta = self.inspector.inspect_file(temp_path)
            return content_hash, total_bytes, audio_meta, temp_path
        except Exception:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise

    async def _resolve_artifact(
        self,
        content_hash: str,
        total_bytes: int,
        audio_meta: AudioMetadata,
        lead_id: str,
        temp_path: str,
        correlation_id: str,
    ) -> tuple[Artifact, bool]:
        storage_key = (
            f"recordings/artifacts/{content_hash[:2]}/{content_hash[:8]}/{content_hash}.wav"
        )
        content_type = "audio/wav"

        existing_artifact = await self.uow.artifacts.get_by_content_hash(content_hash)
        if existing_artifact:
            logger.info(
                "content_hash_duplicate_detected",
                content_hash=content_hash,
                artifact_id=existing_artifact.id,
                correlation_id=correlation_id,
            )
            RECORDING_INGESTION_TOTAL.labels(status="duplicate_content").inc()
            return existing_artifact, True

        if not await self.storage.object_exists(self.bucket_name, storage_key):
            await self.storage.upload_file(self.bucket_name, storage_key, temp_path, content_type)

        new_art = Artifact(
            id=str(uuid.uuid4()),
            lead_id=lead_id,
            storage_key=storage_key,
            content_hash=content_hash,
            content_type=content_type,
            size_bytes=total_bytes,
            duration_seconds=audio_meta.duration_seconds,
            created_at=datetime.now(UTC),
            metadata={
                "channels": audio_meta.channels,
                "sample_rate": audio_meta.sample_rate,
                "bit_depth": audio_meta.bit_depth,
                "format": audio_meta.format_name,
            },
        )
        artifact, is_new = await self.uow.artifacts.save_artifact_idempotent(new_art)
        return artifact, not is_new

    async def _save_recording(
        self,
        sale_id: str,
        artifact_id: str,
        dialler_call_id: str,
        duration_seconds: float,
        call_date: datetime,
    ) -> tuple[Recording, bool]:
        recording_entity = Recording(
            id=str(uuid.uuid4()),
            sale_id=sale_id,
            artifact_id=artifact_id,
            dialler_call_id=dialler_call_id,
            duration_seconds=duration_seconds,
            call_date=call_date,
            created_at=datetime.now(UTC),
        )
        return await self.uow.transcripts.save_recording_idempotent(recording_entity)

    async def _resolve_transcription_job(
        self, content_hash: str, recording_id: str, correlation_id: str
    ) -> tuple[PipelineJob, bool]:
        job_idempotency_key = f"transcription:{content_hash}:{self.processor_version}"
        existing_job = await self.uow.jobs.get_by_idempotency_key(job_idempotency_key)
        if existing_job:
            logger.info(
                "transcription_job_already_exists",
                job_id=existing_job.id,
                idempotency_key=job_idempotency_key,
                correlation_id=correlation_id,
            )
            return existing_job, False

        new_job = PipelineJob(
            id=str(uuid.uuid4()),
            recording_id=recording_id,
            stage="TRANSCRIBING",
            status=JobStatus.QUEUED,
            idempotency_key=job_idempotency_key,
            max_retries=self.max_job_retries,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        return await self.uow.jobs.save_job_idempotent(new_job)

    async def _record_audit_event(
        self,
        recording_id: str,
        artifact_id: str,
        content_hash: str,
        duration_seconds: float,
        is_content_duplicate: bool,
        job_id: str,
        correlation_id: str,
    ) -> None:
        audit_event = AuditEvent(
            id=str(uuid.uuid4()),
            entity_type="RECORDING",
            entity_id=recording_id,
            action="INGESTED",
            actor_type=ActorType.SYSTEM,
            actor_id="ingestion-service",
            correlation_id=correlation_id,
            payload_json={
                "artifact_id": artifact_id,
                "content_hash": content_hash,
                "duration_seconds": duration_seconds,
                "is_content_duplicate": is_content_duplicate,
                "job_id": job_id,
            },
            created_at=datetime.now(UTC),
        )
        await self.uow.audit.record_event(audit_event)

    async def _dispatch_to_queue(
        self, job_id: str, recording_id: str, artifact_id: str, correlation_id: str
    ) -> None:
        if not self.queue:
            return
        try:
            await self.queue.enqueue(
                "transcription",
                {
                    "job_id": job_id,
                    "recording_id": recording_id,
                    "artifact_id": artifact_id,
                    "correlation_id": correlation_id,
                },
            )
        except Exception as exc:
            logger.warning(
                "redis_dispatch_failed_job_queued_in_db",
                job_id=job_id,
                error=str(exc),
                correlation_id=correlation_id,
            )

    def _record_metrics(
        self, start_time: datetime, duration_seconds: float, total_bytes: int
    ) -> None:
        duration_s = (datetime.now(UTC) - start_time).total_seconds()
        RECORDING_INGESTION_DURATION_SECONDS.observe(duration_s)
        RECORDING_AUDIO_DURATION_SECONDS.observe(duration_seconds)
        RECORDING_FILE_SIZE_BYTES.observe(total_bytes)
        RECORDING_INGESTION_TOTAL.labels(status="success").inc()

    async def _stream_to_file(self, source: Any, dest_file: Any, hasher: Any) -> int:
        chunk_size = 1024 * 1024
        total_bytes = 0

        if isinstance(source, (bytes, bytearray)):
            hasher.update(source)
            dest_file.write(source)
            return len(source)

        while True:
            if hasattr(source, "read") and asyncio.iscoroutinefunction(source.read):
                chunk = await source.read(chunk_size)
            elif hasattr(source, "read"):
                chunk = source.read(chunk_size)
            else:
                break

            if not chunk:
                break

            total_bytes += len(chunk)
            hasher.update(chunk)
            dest_file.write(chunk)

        if hasattr(source, "seek"):
            if asyncio.iscoroutinefunction(source.seek):
                await source.seek(0)
            else:
                try:
                    source.seek(0)
                except Exception:
                    pass

        return total_bytes
