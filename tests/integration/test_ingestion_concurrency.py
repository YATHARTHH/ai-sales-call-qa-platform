"""Concurrency and failure mode integration tests for recording ingestion."""

import asyncio
import io
import os
import tempfile
import wave
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from packages.application.ports.audio import AudioInspectorPort, AudioMetadata
from packages.application.ports.queue import QueuePort
from packages.application.ports.storage import StoragePort
from packages.application.services.ingestion_service import IngestionService
from packages.domain.jobs import JobStatus
from packages.domain.retail import Agent, Campaign, Lead, Retailer, Sale
from packages.infrastructure.database.base import Base
from packages.infrastructure.database.models.artifacts import ArtifactModel
from packages.infrastructure.database.models.jobs import PipelineJobModel
from packages.infrastructure.database.models.transcripts import RecordingModel
from packages.infrastructure.database.repositories.sale_repository import SqlAlchemySaleRepository
from packages.infrastructure.database.repositories.unit_of_work import SqlAlchemyUnitOfWork


def create_test_wav_bytes(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        num_frames = int(sample_rate * duration_seconds)
        wf.writeframes(b"\x00" * (num_frames * 2))
    return buf.getvalue()


class SpyStorage(StoragePort):
    def __init__(self):
        self.uploaded_keys = []
        self.objects = {}
    async def upload_object(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        self.uploaded_keys.append(key)
        self.objects[key] = data
    async def upload_file(self, bucket: str, key: str, file_path: str, content_type: str) -> None:
        self.uploaded_keys.append(key)
        with open(file_path, "rb") as f:
            self.objects[key] = f.read()
    async def download_object(self, bucket: str, key: str) -> bytes: return self.objects[key]
    async def bucket_exists(self, bucket: str) -> bool: return True
    async def object_exists(self, bucket: str, key: str) -> bool: return key in self.objects
    async def delete_object(self, bucket: str, key: str) -> None: self.objects.pop(key, None)
    async def get_presigned_url(self, bucket: str, key: str, expires_in_seconds: int = 3600) -> str: return "url"
    async def check_connection(self) -> bool: return True


class SpyAudioInspector(AudioInspectorPort):
    def inspect_file(self, file_path: str) -> AudioMetadata:
        return AudioMetadata(
            duration_seconds=2.0,
            channels=1,
            sample_rate=16000,
            bit_depth=16,
            format_name="WAV",
            num_frames=32000,
            size_bytes=64000,
        )
    def inspect_stream(self, stream, size_bytes): return self.inspect_file("dummy")


class SpyQueue(QueuePort):
    def __init__(self, should_fail: bool = False):
        self.messages = []
        self.should_fail = should_fail
    async def enqueue(self, queue_name: str, payload: dict) -> None:
        if self.should_fail:
            raise ConnectionError("Redis server connection failed")
        self.messages.append((queue_name, payload))
    async def dequeue(self, queue_name: str, timeout_seconds: int = 0): return None
    async def check_connection(self) -> bool: return not self.should_fail


@pytest.fixture
async def shared_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed sale
    async with session_factory() as session:
        now = datetime.now(UTC)
        sale_repo = SqlAlchemySaleRepository(session)
        retailer = Retailer(id="ret-c-1", code="RET_ORIGIN", name="Origin", vertical="ENERGY")
        await sale_repo.save_retailer(retailer)
        campaign = Campaign(id="camp-c-1", code="CAMP_INBOUND", name="Inbound")
        await sale_repo.save_campaign(campaign)
        agent = Agent(id="agent-c-1", staff_id="STF_001", name="Agent", email="ag@ex.com")
        await sale_repo.save_agent(agent)
        lead = Lead(
            id="lead-c-1",
            customer_name="Cust",
            customer_email="cust@ex.com",
            phone="0412345678",
            suburb="Mel",
            state="VIC",
            postcode="3000",
        )
        await sale_repo.save_lead(lead)
        sale = Sale.create(
            sale_id="sale-c-1",
            lead_id="lead-c-1",
            retailer_id="ret-c-1",
            campaign_id="camp-c-1",
            agent_id="agent-c-1",
            sale_date=now,
            product_details={"plan": "Plan"},
        )
        await sale_repo.save_sale(sale)
        await session.commit()

    yield session_factory
    await engine.dispose()
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_concurrent_identical_uploads_deduplicate(shared_db):
    session_factory = shared_db
    wav_bytes = create_test_wav_bytes(duration_seconds=2.0)
    storage = SpyStorage()
    inspector = SpyAudioInspector()
    queue = SpyQueue()

    async with session_factory() as session1, session_factory() as session2:
        uow1 = SqlAlchemyUnitOfWork(session1)
        service1 = IngestionService(uow=uow1, storage=storage, inspector=inspector, queue=queue)
        uow2 = SqlAlchemyUnitOfWork(session2)
        service2 = IngestionService(uow=uow2, storage=storage, inspector=inspector, queue=queue)

        # Concurrent requests: Request A and Request B with identical audio bytes
        resp_a, resp_b = await asyncio.gather(
            service1.ingest_uploaded_audio(
                sale_id="sale-c-1",
                dialler_call_id="dialler-race-1",
                call_date=datetime.now(UTC),
                file_source=wav_bytes,
                correlation_id="corr-race-1",
            ),
            service2.ingest_uploaded_audio(
                sale_id="sale-c-1",
                dialler_call_id="dialler-race-2",
                call_date=datetime.now(UTC),
                file_source=wav_bytes,
                correlation_id="corr-race-2",
            ),
        )

    # Both responses are valid, but share the same Artifact and Job
    assert resp_a.artifact_id == resp_b.artifact_id
    assert resp_a.content_hash == resp_b.content_hash
    assert resp_a.job_id == resp_b.job_id
    assert resp_a.recording_id != resp_b.recording_id

    # Check DB truth:
    async with session_factory() as verify_session:
        # 1. Exactly 1 Artifact
        art_count = (await verify_session.execute(select(func.count(ArtifactModel.id)))).scalar_one()
        assert art_count == 1

        # 2. Exactly 2 Recordings
        rec_count = (await verify_session.execute(select(func.count(RecordingModel.id)))).scalar_one()
        assert rec_count == 2

        # 3. Exactly 1 PipelineJob
        job_count = (await verify_session.execute(select(func.count(PipelineJobModel.id)))).scalar_one()
        assert job_count == 1

    # 4. Storage object stored exactly once
    assert len(storage.objects) == 1

    # 5. Exactly 1 Redis queue dispatch
    assert len(queue.messages) == 1


@pytest.mark.asyncio
async def test_db_commit_succeeds_and_job_queued_when_redis_unavailable(shared_db):
    session_factory = shared_db
    wav_bytes = create_test_wav_bytes(duration_seconds=1.0)
    storage = SpyStorage()
    inspector = SpyAudioInspector()
    failing_queue = SpyQueue(should_fail=True)

    async with session_factory() as session:
        uow = SqlAlchemyUnitOfWork(session)
        service = IngestionService(uow=uow, storage=storage, inspector=inspector, queue=failing_queue)

        # Ingestion must succeed despite Redis transport failure
        resp = await service.ingest_uploaded_audio(
            sale_id="sale-c-1",
            dialler_call_id="dialler-redis-down",
            call_date=datetime.now(UTC),
            file_source=wav_bytes,
            correlation_id="corr-redis-down",
        )

        assert resp.recording_id is not None
        assert resp.job_id is not None

    # Verify DB durable state: Job must exist with status=QUEUED
    async with session_factory() as verify_session:
        stmt = select(PipelineJobModel).where(PipelineJobModel.id == resp.job_id)
        job = (await verify_session.execute(stmt)).scalar_one()
        assert job.status == JobStatus.QUEUED.value
        assert job.recording_id == resp.recording_id
