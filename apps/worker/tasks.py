"""Background worker task execution functions."""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from packages.domain.jobs import FailureCategory, JobStatus, PipelineJob, RetryPolicy
from packages.infrastructure.database.models.jobs import PipelineJobModel
from packages.infrastructure.database.session import async_session_factory
from packages.observability.logging import get_logger
from packages.observability.metrics import (
    WORKER_JOB_DURATION_SECONDS,
    WORKER_JOBS_TOTAL,
)

logger = get_logger("worker.tasks")


async def execute_smoke_job(
    job_id: str, worker_id: str, correlation_id: str, session_factory=None
) -> None:
    """Execute smoke test job verifying durable state persistence and metrics."""
    logger.info(
        "smoke_job_started", job_id=job_id, worker_id=worker_id, correlation_id=correlation_id
    )
    start_time = datetime.now(UTC)

    factory = session_factory or async_session_factory
    async with factory() as session:
        # 1. Fetch durable job from PostgreSQL
        stmt = select(PipelineJobModel).where(PipelineJobModel.id == job_id)
        result = await session.execute(stmt)
        job_model = result.scalar_one_or_none()

        if not job_model:
            logger.error("job_not_found_in_db", job_id=job_id)
            return

        # 2. Acquire worker lease
        job = PipelineJob(
            id=job_model.id,
            recording_id=job_model.recording_id,
            stage=job_model.stage,
            status=JobStatus(job_model.status),
            idempotency_key=job_model.idempotency_key,
            retry_count=job_model.retry_count,
            max_retries=job_model.max_retries,
        )
        job.acquire_lease(worker_id=worker_id)
        job_model.status = job.status.value
        job_model.worker_id = job.worker_id
        job_model.heartbeat_at = job.heartbeat_at
        job_model.lease_until = job.lease_until
        job_model.started_at = job.started_at
        await session.commit()

        # 3. Simulate processing work
        await asyncio.sleep(0.5)

        # 4. Mark job completed
        job.mark_completed()
        job_model.status = job.status.value
        job_model.completed_at = job.completed_at
        job_model.lease_until = None
        await session.commit()

        duration = (datetime.now(UTC) - start_time).total_seconds()
        WORKER_JOBS_TOTAL.labels(stage=job.stage, status="COMPLETED").inc()
        WORKER_JOB_DURATION_SECONDS.labels(stage=job.stage).observe(duration)

        logger.info(
            "smoke_job_completed",
            job_id=job_id,
            duration_s=duration,
            status=job.status.value,
        )


async def recover_stale_jobs(policy: RetryPolicy | None = None, session_factory=None) -> int:
    """Identify and reclaim jobs left in RUNNING whose lease has expired."""
    active_policy = policy or RetryPolicy()
    recovered_count = 0
    now = datetime.now(UTC)

    factory = session_factory or async_session_factory
    async with factory() as session:
        stmt = select(PipelineJobModel).where(
            PipelineJobModel.status == JobStatus.RUNNING.value,
            PipelineJobModel.lease_until < now,
        )
        result = await session.execute(stmt)
        stale_jobs = result.scalars().all()

        for job_model in stale_jobs:
            logger.warning(
                "stale_job_detected",
                job_id=job_model.id,
                lease_until=job_model.lease_until.isoformat() if job_model.lease_until else None,
                worker_id=job_model.worker_id,
            )

            # Check if job should be retried or dead-lettered
            if active_policy.should_retry(FailureCategory.TRANSIENT, job_model.retry_count):
                job_model.retry_count += 1
                job_model.status = JobStatus.QUEUED.value
                job_model.last_error = "Worker lease expired; job reclaimed by recovery routine."
                logger.info(
                    "stale_job_requeued", job_id=job_model.id, retry_count=job_model.retry_count
                )
            else:
                job_model.status = JobStatus.DEAD_LETTER.value
                job_model.last_error = "Worker lease expired and max retries exceeded."
                logger.error("stale_job_dead_lettered", job_id=job_model.id)

            job_model.lease_until = None
            recovered_count += 1

        if recovered_count > 0:
            await session.commit()

    return recovered_count
