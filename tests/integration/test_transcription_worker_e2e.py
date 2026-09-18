"""End-to-end integration tests for transcription worker, lease fencing, and transactional rollback."""

import hashlib
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

from apps.worker.tasks import execute_transcription_job
from packages.application.ports.queue import QueuePort
from packages.application.ports.storage import StoragePort
from packages.domain.exceptions import LeaseLostError
from packages.domain.jobs import JobStatus
from packages.domain.retail import Agent, Campaign, Lead, Retailer, Sale
from packages.domain.transcript import Recording, TranscriptAvailability
from packages.infrastructure.database.models.artifacts import ArtifactModel
from packages.infrastructure.database.models.evaluations import AuditEventModel
from packages.infrastructure.database.models.jobs import PipelineJobModel
from packages.infrastructure.database.models.transcripts import (
    TranscriptModel,
    TranscriptSegmentModel,
)
from packages.infrastructure.database.repositories.job_repository import (
    SqlAlchemyJobRepository,
)
from packages.infrastructure.database.repositories.sale_repository import (
    SqlAlchemySaleRepository,
)
from packages.infrastructure.database.repositories.transcript_repository import (
    SqlAlchemyTranscriptRepository,
)
from packages.infrastructure.transcription.deterministic_adapter import (
    DeterministicTranscriptionAdapter,
)
from packages.infrastructure.transcription.role_resolver import (
    HeuristicSpeakerRoleResolver,
)


class InMemoryStorage(StoragePort):
    def __init__(self):
        self.objects = {}

    async def upload_object(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        self.objects[f"{bucket}/{key}"] = data

    async def upload_file(self, bucket: str, key: str, file_path: str, content_type: str) -> None:
        with open(file_path, "rb") as f:
            self.objects[f"{bucket}/{key}"] = f.read()

    async def download_object(self, bucket: str, key: str) -> bytes:
        return self.objects.get(f"{bucket}/{key}", b"")

    async def bucket_exists(self, bucket: str) -> bool:
        return True

    async def object_exists(self, bucket: str, key: str) -> bool:
        return f"{bucket}/{key}" in self.objects

    async def delete_object(self, bucket: str, key: str) -> None:
        self.objects.pop(f"{bucket}/{key}", None)

    async def get_presigned_url(self, bucket: str, key: str, expires_in_seconds: int = 3600) -> str:
        return f"https://in-memory/{bucket}/{key}"

    async def check_connection(self) -> bool:
        return True


class InMemoryQueue(QueuePort):
    def __init__(self):
        self.enqueued = []

    async def enqueue(self, queue_name: str, payload: dict[str, Any]) -> None:
        self.enqueued.append((queue_name, payload))

    async def dequeue(self, queue_name: str, timeout: int = 0) -> dict[str, Any] | None:
        return None

    async def check_connection(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_transcription_worker_full_lifecycle_and_replay(test_db_session):
    """Full lifecycle: audio materialization -> transcription -> lease fence -> evaluation dispatch -> replay."""
    now = datetime.now(UTC)
    sale_repo = SqlAlchemySaleRepository(test_db_session)
    tr_repo = SqlAlchemyTranscriptRepository(test_db_session)

    # 1. Setup base commercial records
    ret = Retailer(id="ret-e2e", code="RET_E2E", name="E2E Retailer")
    camp = Campaign(id="camp-e2e", code="CAMP_E2E", name="E2E Campaign")
    agt = Agent(id="agt-e2e", staff_id="STF_E2E", name="Sarah", email="s@test.com")
    lead = Lead(id="lead-e2e", customer_name="Jane Smith", customer_email="j@test.com", phone="0400000000")
    sale = Sale.create("lead-e2e", "ret-e2e", "camp-e2e", "agt-e2e", now, {}, sale_id="sale-e2e")
    await sale_repo.save_retailer(ret)
    await sale_repo.save_campaign(camp)
    await sale_repo.save_agent(agt)
    await sale_repo.save_lead(lead)
    await sale_repo.save_sale(sale)

    # 2. Setup mock audio artifact and recording
    raw_audio = b"RIFF" + b"\x00" * 1024
    audio_hash = hashlib.sha256(raw_audio).hexdigest()
    storage = InMemoryStorage()
    await storage.upload_object("sales-call-recordings", "recordings/call_e2e.wav", raw_audio, "audio/wav")

    audio_art = ArtifactModel(
        id="art-audio-e2e",
        lead_id="lead-e2e",
        storage_key="recordings/call_e2e.wav",
        content_hash=audio_hash,
        content_type="audio/wav",
        size_bytes=len(raw_audio),
        metadata_json={},
        created_at=now,
    )
    test_db_session.add(audio_art)
    await test_db_session.flush()

    recording = Recording.create(
        sale_id="sale-e2e",
        artifact_id="art-audio-e2e",
        dialler_call_id="DIALLER_E2E_001",
        duration_seconds=1800.0,  # 30 min
        call_date=now,
        recording_id="rec-e2e",
    )
    await tr_repo.save_recording(recording)

    # 3. Create PipelineJob in QUEUED status
    tx_job = PipelineJobModel(
        id="job-tx-e2e",
        recording_id="rec-e2e",
        stage="TRANSCRIBING",
        status=JobStatus.QUEUED.value,
        idempotency_key="key-tx-e2e",
        lease_generation=0,
        created_at=now,
        updated_at=now,
    )
    test_db_session.add(tx_job)
    await test_db_session.commit()

    queue = InMemoryQueue()

    # Define session factory returning the test db session
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def session_factory():
        yield test_db_session

    # 4. Execute transcription job
    await execute_transcription_job(
        job_id="job-tx-e2e",
        worker_id="worker-test-1",
        correlation_id="corr-e2e",
        transcriber=DeterministicTranscriptionAdapter(),
        role_resolver=HeuristicSpeakerRoleResolver(),
        session_factory=session_factory,
        storage_adapter=storage,
        queue_adapter=queue,
    )
    test_db_session.expire_all()

    # 5. Verify database records
    stmt = select(TranscriptModel).where(TranscriptModel.recording_id == "rec-e2e")
    res = await test_db_session.execute(stmt)
    transcript = res.scalar_one()

    assert transcript is not None
    assert transcript.availability == TranscriptAvailability.AVAILABLE.value
    assert transcript.audio_duration_ms == 1800000
    assert len(transcript.transcription_key) == 64
    assert transcript.transcription_identity.startswith("transcription:")
    assert transcript.behavior_json is not None

    # Check segments
    seg_stmt = (
        select(TranscriptSegmentModel)
        .where(TranscriptSegmentModel.transcript_id == transcript.id)
        .order_by(TranscriptSegmentModel.segment_order.asc())
    )
    seg_res = await test_db_session.execute(seg_stmt)
    segments = seg_res.scalars().all()
    assert len(segments) >= 8
    assert segments[0].business_role == "AGENT"
    assert segments[1].business_role == "CUSTOMER"

    # Check transcribing job completed
    job_repo = SqlAlchemyJobRepository(test_db_session)
    completed_tx_job = await job_repo.get_by_id("job-tx-e2e")
    assert completed_tx_job.status == JobStatus.COMPLETED
    assert completed_tx_job.lease_until is None

    # Check downstream evaluation job created
    eval_stmt = select(PipelineJobModel).where(
        PipelineJobModel.recording_id == "rec-e2e",
        PipelineJobModel.stage == "EVALUATING",
    )
    eval_res = await test_db_session.execute(eval_stmt)
    eval_job = eval_res.scalar_one()
    assert eval_job.status == JobStatus.QUEUED.value
    assert eval_job.idempotency_key.startswith("rec-e2e:EVALUATING:")

    # Check Redis queue message
    assert len(queue.enqueued) == 1
    q_name, q_payload = queue.enqueued[0]
    assert q_name == "queue:evaluation"
    assert q_payload["recording_id"] == "rec-e2e"
    assert q_payload["job_id"] == eval_job.id

    # 6. Test Idempotent Replay
    # Re-running the job should detect existing transcript, complete, and not duplicate records
    queue.enqueued.clear()
    await execute_transcription_job(
        job_id="job-tx-e2e",
        worker_id="worker-test-1",
        session_factory=session_factory,
        storage_adapter=storage,
        queue_adapter=queue,
    )
    # Ensure no duplicate transcripts
    count_stmt = select(TranscriptModel).where(TranscriptModel.recording_id == "rec-e2e")
    all_txs = (await test_db_session.execute(count_stmt)).scalars().all()
    assert len(all_txs) == 1


@pytest.mark.asyncio
async def test_transcription_lease_loss_rolls_back_entire_transaction(test_db_session):
    """Failure-injection test: worker loses lease before commit; entire transaction rolls back."""
    now = datetime.now(UTC)
    sale_repo = SqlAlchemySaleRepository(test_db_session)
    tr_repo = SqlAlchemyTranscriptRepository(test_db_session)

    # 1. Setup base commercial records
    ret = Retailer(id="ret-loss", code="RET_LOSS", name="Loss Retailer")
    camp = Campaign(id="camp-loss", code="CAMP_LOSS", name="Loss Campaign")
    agt = Agent(id="agt-loss", staff_id="STF_LOSS", name="Sarah", email="s2@test.com")
    lead = Lead(id="lead-loss", customer_name="Jane Smith", customer_email="j2@test.com", phone="0400000000")
    sale = Sale.create("lead-loss", "ret-loss", "camp-loss", "agt-loss", now, {}, sale_id="sale-loss")
    await sale_repo.save_retailer(ret)
    await sale_repo.save_campaign(camp)
    await sale_repo.save_agent(agt)
    await sale_repo.save_lead(lead)
    await sale_repo.save_sale(sale)

    # 2. Audio artifact and recording
    raw_audio = b"RIFF" + b"\x00" * 1024
    audio_hash = hashlib.sha256(raw_audio).hexdigest()
    storage = InMemoryStorage()
    await storage.upload_object("sales-call-recordings", "recordings/call_loss.wav", raw_audio, "audio/wav")

    audio_art = ArtifactModel(
        id="art-audio-loss",
        lead_id="lead-loss",
        storage_key="recordings/call_loss.wav",
        content_hash=audio_hash,
        content_type="audio/wav",
        size_bytes=len(raw_audio),
        metadata_json={},
        created_at=now,
    )
    test_db_session.add(audio_art)
    await test_db_session.flush()

    recording = Recording.create(
        sale_id="sale-loss",
        artifact_id="art-audio-loss",
        dialler_call_id="DIALLER_LOSS_001",
        duration_seconds=1800.0,
        call_date=now,
        recording_id="rec-loss",
    )
    await tr_repo.save_recording(recording)

    tx_job = PipelineJobModel(
        id="job-tx-loss",
        recording_id="rec-loss",
        stage="TRANSCRIBING",
        status=JobStatus.QUEUED.value,
        idempotency_key="key-tx-loss",
        lease_generation=0,
        created_at=now,
        updated_at=now,
    )
    test_db_session.add(tx_job)
    await test_db_session.commit()

    queue = InMemoryQueue()

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def session_factory():
        yield test_db_session

    # Custom transcriber that simulates lease loss by bumping lease_generation in DB during execution
    class LeaseHijackingTranscriber(DeterministicTranscriptionAdapter):
        async def transcribe(self, source):
            # Another worker hijacks the lease by bumping lease_generation to 999
            await test_db_session.execute(
                select(PipelineJobModel).where(PipelineJobModel.id == "job-tx-loss")
            )
            job = await test_db_session.get(PipelineJobModel, "job-tx-loss")
            job.lease_generation = 999
            await test_db_session.flush()
            return await super().transcribe(source)

    # 3. Execute transcription job - must raise LeaseLostError
    with pytest.raises(LeaseLostError):
        await execute_transcription_job(
            job_id="job-tx-loss",
            worker_id="worker-stale",
            session_factory=session_factory,
            storage_adapter=storage,
            queue_adapter=queue,
            transcriber=LeaseHijackingTranscriber(),
        )

    # 4. Assert full rollback: Transcript, Segments, Evaluation Job, Audit, Redis
    tx_check = await test_db_session.execute(
        select(TranscriptModel).where(TranscriptModel.recording_id == "rec-loss")
    )
    assert tx_check.scalar_one_or_none() is None

    seg_check = await test_db_session.execute(
        select(TranscriptSegmentModel).where(TranscriptSegmentModel.transcript_id == "tx-rec-loss")
    )
    assert len(seg_check.scalars().all()) == 0

    eval_check = await test_db_session.execute(
        select(PipelineJobModel).where(
            PipelineJobModel.recording_id == "rec-loss",
            PipelineJobModel.stage == "EVALUATING",
        )
    )
    assert eval_check.scalar_one_or_none() is None

    audit_check = await test_db_session.execute(
        select(AuditEventModel).where(AuditEventModel.entity_id == "tx-rec-loss")
    )
    assert len(audit_check.scalars().all()) == 0

    # Redis queue must have zero messages published
    assert len(queue.enqueued) == 0
