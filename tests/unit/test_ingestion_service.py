"""Unit tests for IngestionService domain orchestration and deduplication logic."""

import io
import wave
from datetime import UTC, datetime

import pytest

from packages.application.ports.audio import AudioInspectorPort, AudioMetadata
from packages.application.ports.queue import QueuePort
from packages.application.ports.repositories import (
    ArtifactRepositoryPort,
    AuditRepositoryPort,
    JobRepositoryPort,
    SaleRepositoryPort,
    TranscriptRepositoryPort,
    UnitOfWorkPort,
)
from packages.application.ports.storage import StoragePort
from packages.application.services.ingestion_service import IngestionService
from packages.domain.exceptions import DomainError
from packages.domain.jobs import JobStatus
from packages.domain.retail import Sale


def create_test_wav_bytes(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        num_frames = int(sample_rate * duration_seconds)
        wf.writeframes(b"\x00" * (num_frames * 2))
    return buf.getvalue()


class MockSaleRepo(SaleRepositoryPort):
    def __init__(self):
        self.sales = {}
    async def save_retailer(self, retailer): pass
    async def get_retailer(self, retailer_id): return None
    async def save_campaign(self, campaign): pass
    async def save_agent(self, agent): pass
    async def save_lead(self, lead): pass
    async def get_lead(self, lead_id): return None
    async def save_sale(self, sale): self.sales[sale.id] = sale
    async def get_sale(self, sale_id): return self.sales.get(sale_id)


class MockTranscriptRepo(TranscriptRepositoryPort):
    def __init__(self):
        self.recordings = {}
        self.dialler_map = {}
    async def save_recording(self, recording):
        self.recordings[recording.id] = recording
        self.dialler_map[recording.dialler_call_id] = recording
    async def get_recording(self, recording_id): return self.recordings.get(recording_id)
    async def get_recording_by_dialler_id(self, dialler_call_id): return self.dialler_map.get(dialler_call_id)
    async def save_recording_idempotent(self, recording):
        if recording.dialler_call_id in self.dialler_map:
            return self.dialler_map[recording.dialler_call_id], False
        self.recordings[recording.id] = recording
        self.dialler_map[recording.dialler_call_id] = recording
        return recording, True
    async def save_transcript(self, transcript, segments): pass
    async def get_transcript(self, transcript_id): return None
    async def get_transcript_segments(self, transcript_id): return []


class MockArtifactRepo(ArtifactRepositoryPort):
    def __init__(self):
        self.artifacts = {}
        self.hash_map = {}
    async def get_by_id(self, artifact_id): return self.artifacts.get(artifact_id)
    async def get_by_content_hash(self, content_hash): return self.hash_map.get(content_hash)
    async def save_artifact_idempotent(self, artifact):
        if artifact.content_hash in self.hash_map:
            return self.hash_map[artifact.content_hash], False
        self.artifacts[artifact.id] = artifact
        self.hash_map[artifact.content_hash] = artifact
        return artifact, True


class MockJobRepo(JobRepositoryPort):
    def __init__(self):
        self.jobs = {}
        self.key_map = {}
    async def get_by_id(self, job_id): return self.jobs.get(job_id)
    async def get_by_idempotency_key(self, idempotency_key): return self.key_map.get(idempotency_key)
    async def save_job_idempotent(self, job):
        if job.idempotency_key in self.key_map:
            return self.key_map[job.idempotency_key], False
        self.jobs[job.id] = job
        self.key_map[job.idempotency_key] = job
        return job, True


class MockAuditRepo(AuditRepositoryPort):
    def __init__(self):
        self.events = []
    async def record_event(self, event): self.events.append(event)
    async def get_events_for_entity(self, entity_type, entity_id): return self.events


class MockUnitOfWork(UnitOfWorkPort):
    def __init__(self):
        self.sales = MockSaleRepo()
        self.transcripts = MockTranscriptRepo()
        self.artifacts = MockArtifactRepo()
        self.jobs = MockJobRepo()
        self.audit = MockAuditRepo()
        self.committed = False
        self.rolled_back = False
    async def commit(self): self.committed = True
    async def rollback(self): self.rolled_back = True


class MockStorage(StoragePort):
    def __init__(self):
        self.objects = {}
    async def upload_object(self, bucket, key, data, content_type): self.objects[key] = data
    async def upload_file(self, bucket, key, file_path, content_type):
        with open(file_path, "rb") as f:
            self.objects[key] = f.read()
    async def download_object(self, bucket, key): return self.objects[key]
    async def bucket_exists(self, bucket): return True
    async def object_exists(self, bucket, key): return key in self.objects
    async def delete_object(self, bucket, key): self.objects.pop(key, None)
    async def get_presigned_url(self, bucket, key, expires_in_seconds=3600): return f"http://localhost:9000/{bucket}/{key}"
    async def check_connection(self): return True


class MockAudioInspector(AudioInspectorPort):
    def inspect_file(self, file_path):
        return AudioMetadata(
            duration_seconds=1.5,
            channels=1,
            sample_rate=16000,
            bit_depth=16,
            format_name="WAV",
            num_frames=24000,
            size_bytes=48000,
        )
    def inspect_stream(self, stream, size_bytes):
        return self.inspect_file("dummy")


class MockQueue(QueuePort):
    def __init__(self, should_fail=False):
        self.messages = []
        self.should_fail = should_fail
    async def enqueue(self, queue_name, payload):
        if self.should_fail:
            raise ConnectionError("Simulated Redis transport failure")
        self.messages.append((queue_name, payload))
    async def dequeue(self, queue_name, timeout_seconds=0): return None
    async def check_connection(self): return True


@pytest.fixture
def setup_env():
    uow = MockUnitOfWork()
    storage = MockStorage()
    inspector = MockAudioInspector()
    queue = MockQueue()
    sale = Sale.create(
        sale_id="sale-100",
        lead_id="lead-200",
        retailer_id="ret-1",
        campaign_id="camp-1",
        agent_id="agent-1",
        sale_date=datetime.now(UTC),
        product_details={"plan": "Standard"},
    )
    uow.sales.sales["sale-100"] = sale
    service = IngestionService(uow=uow, storage=storage, inspector=inspector, queue=queue)
    return service, uow, storage, queue


@pytest.mark.asyncio
async def test_ingest_valid_audio_creates_all_entities(setup_env):
    service, uow, storage, queue = setup_env
    audio_bytes = create_test_wav_bytes(duration_seconds=1.5)

    resp = await service.ingest_uploaded_audio(
        sale_id="sale-100",
        dialler_call_id="call-1001",
        call_date=datetime.now(UTC),
        file_source=audio_bytes,
        correlation_id="corr-1",
    )

    assert resp.sale_id == "sale-100"
    assert resp.dialler_call_id == "call-1001"
    assert resp.is_duplicate is False
    assert resp.job_id is not None
    assert uow.committed is True
    assert len(uow.artifacts.artifacts) == 1
    assert len(uow.transcripts.recordings) == 1
    assert len(uow.jobs.jobs) == 1
    assert len(queue.messages) == 1
    assert len(uow.audit.events) == 1
    assert uow.audit.events[0].action == "INGESTED"


@pytest.mark.asyncio
async def test_ingest_rejects_missing_sale(setup_env):
    service, _, _, _ = setup_env
    audio_bytes = create_test_wav_bytes()

    with pytest.raises(DomainError) as exc:
        await service.ingest_uploaded_audio(
            sale_id="non-existent-sale",
            dialler_call_id="call-1002",
            call_date=datetime.now(UTC),
            file_source=audio_bytes,
            correlation_id="corr-2",
        )
    assert exc.value.code == "SALE_NOT_FOUND"


@pytest.mark.asyncio
async def test_ingest_rejects_empty_audio_file(setup_env):
    service, _, _, _ = setup_env

    with pytest.raises(DomainError) as exc:
        await service.ingest_uploaded_audio(
            sale_id="sale-100",
            dialler_call_id="call-1003",
            call_date=datetime.now(UTC),
            file_source=b"",
            correlation_id="corr-3",
        )
    assert exc.value.code == "EMPTY_AUDIO_FILE"


@pytest.mark.asyncio
async def test_ingest_duplicate_dialler_call_id_returns_existing(setup_env):
    service, uow, storage, queue = setup_env
    audio_bytes = create_test_wav_bytes(duration_seconds=1.5)

    # First upload
    resp1 = await service.ingest_uploaded_audio(
        sale_id="sale-100",
        dialler_call_id="call-dup-1",
        call_date=datetime.now(UTC),
        file_source=audio_bytes,
        correlation_id="corr-dup-1",
    )
    assert resp1.is_duplicate is False

    # Re-upload with exact same dialler_call_id
    resp2 = await service.ingest_uploaded_audio(
        sale_id="sale-100",
        dialler_call_id="call-dup-1",
        call_date=datetime.now(UTC),
        file_source=audio_bytes,
        correlation_id="corr-dup-2",
    )
    assert resp2.is_duplicate is True
    assert resp2.recording_id == resp1.recording_id
    assert resp2.artifact_id == resp1.artifact_id
    assert len(uow.transcripts.recordings) == 1
    assert len(queue.messages) == 1


@pytest.mark.asyncio
async def test_ingest_duplicate_content_hash_reuses_artifact_and_job(setup_env):
    service, uow, storage, queue = setup_env
    audio_bytes = create_test_wav_bytes(duration_seconds=2.0)

    # Recording A
    resp_a = await service.ingest_uploaded_audio(
        sale_id="sale-100",
        dialler_call_id="dialler-A",
        call_date=datetime.now(UTC),
        file_source=audio_bytes,
        correlation_id="corr-A",
    )
    assert resp_a.is_duplicate is False

    # Recording B: different dialler_call_id, but identical audio bytes
    resp_b = await service.ingest_uploaded_audio(
        sale_id="sale-100",
        dialler_call_id="dialler-B",
        call_date=datetime.now(UTC),
        file_source=audio_bytes,
        correlation_id="corr-B",
    )
    # Recording B is a valid new recording entity, but shares Artifact and Job
    assert resp_b.is_duplicate is False
    assert resp_b.recording_id != resp_a.recording_id
    assert resp_b.artifact_id == resp_a.artifact_id
    assert resp_b.content_hash == resp_a.content_hash
    assert resp_b.job_id == resp_a.job_id

    # Golden verification: 1 Artifact, 2 Recordings, 1 Job, 1 Redis message!
    assert len(uow.artifacts.artifacts) == 1
    assert len(uow.transcripts.recordings) == 2
    assert len(uow.jobs.jobs) == 1
    assert len(queue.messages) == 1


@pytest.mark.asyncio
async def test_ingest_redis_dispatch_failure_keeps_job_queued_in_db(setup_env):
    service, uow, storage, queue = setup_env
    queue.should_fail = True
    audio_bytes = create_test_wav_bytes(duration_seconds=1.0)

    # Upload must succeed even if Redis is unavailable
    resp = await service.ingest_uploaded_audio(
        sale_id="sale-100",
        dialler_call_id="call-redis-fail",
        call_date=datetime.now(UTC),
        file_source=audio_bytes,
        correlation_id="corr-redis-fail",
    )

    assert resp.recording_id is not None
    assert uow.committed is True
    job = uow.jobs.jobs[resp.job_id]
    assert job.status == JobStatus.QUEUED
