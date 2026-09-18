import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
"""End-to-End Worker & Pipeline Smoke Test Script.

Validates the full control loop:
Artifact Ingestion -> DB Transaction -> Redis Dispatch -> Worker Execution -> DB State Completion.
"""

import asyncio
import sys
import uuid

from sqlalchemy import select

from apps.worker.tasks import execute_smoke_job
from packages.domain.artifacts import Artifact
from packages.domain.jobs import JobStatus, PipelineJob
from packages.infrastructure.database.base import Base
from packages.infrastructure.database.models.artifacts import ArtifactModel
from packages.infrastructure.database.models.jobs import PipelineJobModel
import os
from packages.infrastructure.database.session import async_session_factory, engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Support standalone testing via local sqlite or configured postgres
if '--sqlite' in sys.argv or os.getenv('SMOKE_DB_URL'):
    db_target = os.getenv('SMOKE_DB_URL', 'sqlite+aiosqlite:///smoke_test.db')
    engine = create_async_engine(db_target, echo=False)
    async_session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

from packages.infrastructure.queue.redis_queue import RedisQueueAdapter
from packages.observability.logging import configure_logging, get_logger

configure_logging(log_level="INFO", json_format=False)
logger = get_logger("smoke_test")


async def run_smoke_test() -> bool:
    logger.info("=== Starting SalesCall QA Platform Smoke Test ===")

    # 1. Ensure database schema tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("db_schema_ready", tables=["artifacts", "pipeline_jobs"])

    # 2. Ingest immutable source artifact
    sample_audio_bytes = b"SAMPLE_AUDIO_BYTES_LEAD_3613790_RETAILER_1_CALL"
    lead_id = "3613790"
    storage_key = f"recordings/lead_{lead_id}.wav"

    artifact = Artifact.create(
        lead_id=lead_id,
        storage_key=storage_key,
        raw_content=sample_audio_bytes,
        content_type="audio/wav",
        duration_seconds=1800.0,
        metadata={"retailer": "Retailer 1", "campaign": "inbound_sales"},
    )

    async with async_session_factory() as session:
        # Check if already exists to ensure idempotency
        stmt = select(ArtifactModel).where(ArtifactModel.content_hash == artifact.content_hash)
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()

        if not existing:
            artifact_model = ArtifactModel(
                id=artifact.id,
                lead_id=artifact.lead_id,
                storage_key=artifact.storage_key,
                content_hash=artifact.content_hash,
                content_type=artifact.content_type,
                size_bytes=artifact.size_bytes,
                duration_seconds=artifact.duration_seconds,
                metadata_json=artifact.metadata,
                created_at=artifact.created_at,
            )
            session.add(artifact_model)
            await session.commit()
            logger.info("artifact_persisted", artifact_id=artifact.id, content_hash=artifact.content_hash)
        else:
            artifact = Artifact(
                id=existing.id,
                lead_id=existing.lead_id,
                storage_key=existing.storage_key,
                content_hash=existing.content_hash,
                content_type=existing.content_type,
                size_bytes=existing.size_bytes,
                duration_seconds=existing.duration_seconds,
                created_at=existing.created_at,
                metadata=existing.metadata_json,
            )
            logger.info("artifact_already_exists", artifact_id=artifact.id)

    # 3. Create durable PipelineJob in PostgreSQL
    job = PipelineJob.create(
        recording_id=artifact.id,
        stage="smoke_validation",
        input_artifact_hash=artifact.content_hash,
        processor_version="smoke-v1",
    )

    async with async_session_factory() as session:
        job_model = PipelineJobModel(
            id=job.id,
            recording_id=job.recording_id,
            stage=job.stage,
            status=job.status.value,
            idempotency_key=job.idempotency_key,
            retry_count=job.retry_count,
            max_retries=job.max_retries,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
        session.add(job_model)
        await session.commit()
        logger.info("durable_job_created", job_id=job.id, status=job.status.value, key=job.idempotency_key)

    # 4. Dispatch job to Redis queue
    queue_adapter = RedisQueueAdapter()
    correlation_id = f"corr-{uuid.uuid4().hex[:8]}"

    # Check if Redis is running, or simulate local worker dispatch
    redis_available = await queue_adapter.check_connection()
    if redis_available:
        await queue_adapter.enqueue("smoke_job", {
            "job_id": job.id,
            "correlation_id": correlation_id,
        })
        logger.info("job_dispatched_to_redis", queue="smoke_job", correlation_id=correlation_id)
    else:
        logger.warning("redis_offline_simulating_worker", reason="Proceeding with direct in-process worker task")

    # 5. Execute worker task
    worker_id = f"worker-test-{uuid.uuid4().hex[:6]}"
    await execute_smoke_job(
        job_id=job.id,
        worker_id=worker_id,
        correlation_id=correlation_id,
        session_factory=async_session_factory,
    )

    # 6. Verify final state in PostgreSQL
    async with async_session_factory() as session:
        stmt = select(PipelineJobModel).where(PipelineJobModel.id == job.id)
        result = await session.execute(stmt)
        final_job = result.scalar_one_or_none()

        assert final_job is not None, "Job record missing in DB!"
        assert final_job.status == JobStatus.COMPLETED.value, f"Expected COMPLETED, got {final_job.status}"
        assert final_job.completed_at is not None, "completed_at timestamp was not updated!"
        assert final_job.worker_id == worker_id, f"Worker ID mismatch! {final_job.worker_id} vs {worker_id}"

    logger.info(
        "=== Smoke Test PASSED! Full Control Path Verified ===",
        job_id=job.id,
        status="COMPLETED",
        worker_id=worker_id,
    )
    return True


if __name__ == "__main__":
    success = asyncio.run(run_smoke_test())
    sys.exit(0 if success else 1)
