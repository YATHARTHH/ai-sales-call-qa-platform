"""SQLAlchemy implementation of JobRepositoryPort."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from packages.application.ports.repositories import JobRepositoryPort
from packages.domain.jobs import FailureCategory, JobStatus, PipelineJob
from packages.infrastructure.database.models.jobs import PipelineJobModel


class SqlAlchemyJobRepository(JobRepositoryPort):
    """Persistence adapter for durable background pipeline jobs."""

    def __init__(self, session: AsyncSession):
        self._session = session

    def _to_domain(self, model: PipelineJobModel) -> PipelineJob:
        return PipelineJob(
            id=model.id,
            recording_id=model.recording_id,
            stage=model.stage,
            status=JobStatus(model.status),
            idempotency_key=model.idempotency_key,
            retry_count=model.retry_count,
            max_retries=model.max_retries,
            last_error=model.last_error,
            failure_category=FailureCategory(model.failure_category)
            if model.failure_category
            else None,
            worker_id=model.worker_id,
            heartbeat_at=model.heartbeat_at,
            lease_until=model.lease_until,
            lease_generation=model.lease_generation,
            started_at=model.started_at,
            completed_at=model.completed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def get_by_id(self, job_id: str) -> PipelineJob | None:
        stmt = (
            select(PipelineJobModel)
            .where(PipelineJobModel.id == job_id)
            .execution_options(populate_existing=True)
        )
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def get_by_idempotency_key(self, idempotency_key: str) -> PipelineJob | None:
        stmt = (
            select(PipelineJobModel)
            .where(PipelineJobModel.idempotency_key == idempotency_key)
            .execution_options(populate_existing=True)
        )
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def save_job_idempotent(self, job: PipelineJob) -> tuple[PipelineJob, bool]:
        """Persist pipeline job, treating uniqueness conflict as expected concurrency outcome."""
        existing = await self.get_by_idempotency_key(job.idempotency_key)
        if existing:
            return existing, False

        model = PipelineJobModel(
            id=job.id,
            recording_id=job.recording_id,
            stage=job.stage,
            status=job.status.value,
            idempotency_key=job.idempotency_key,
            retry_count=job.retry_count,
            max_retries=job.max_retries,
            last_error=job.last_error,
            failure_category=job.failure_category.value if job.failure_category else None,
            worker_id=job.worker_id,
            heartbeat_at=job.heartbeat_at,
            lease_until=job.lease_until,
            lease_generation=job.lease_generation,
            started_at=job.started_at,
            completed_at=job.completed_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

        is_inserted = False
        async with self._session.begin_nested():
            try:
                self._session.add(model)
                await self._session.flush()
                is_inserted = True
            except IntegrityError:
                pass

        if is_inserted:
            return job, True

        winner = await self.get_by_idempotency_key(job.idempotency_key)
        if winner is None:
            for _ in range(30):
                await asyncio.sleep(0.05)
                winner = await self.get_by_idempotency_key(job.idempotency_key)
                if winner is not None:
                    break
        if winner is not None:
            return winner, False
        raise RuntimeError("Failed to resolve job on idempotency_key conflict")

    async def claim_job_lease_atomic(
        self, job_id: str, worker_id: str, lease_duration_seconds: int = 60
    ) -> PipelineJob | None:
        """Atomically claim job lease and increment lease_generation in a single atomic SQL statement."""
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=lease_duration_seconds)

        stmt = (
            update(PipelineJobModel)
            .where(PipelineJobModel.id == job_id)
            .values(
                status=JobStatus.RUNNING.value,
                worker_id=worker_id,
                started_at=PipelineJobModel.started_at or now,
                heartbeat_at=now,
                lease_until=lease_until,
                lease_generation=PipelineJobModel.lease_generation + 1,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
            .returning(*PipelineJobModel.__table__.columns)
        )
        res = await self._session.execute(stmt)
        row = res.one_or_none()
        if not row:
            return None
        await self._session.flush()
        return self._to_domain(row)

    async def complete_job_with_lease_fence(
        self,
        job_id: str,
        worker_id: str,
        lease_generation: int,
        completed_at: datetime | None = None,
    ) -> bool:
        """Atomically mark job COMPLETED only if the worker still owns the valid lease_generation."""
        now = completed_at or datetime.now(UTC)

        stmt = (
            update(PipelineJobModel)
            .where(
                PipelineJobModel.id == job_id,
                PipelineJobModel.worker_id == worker_id,
                PipelineJobModel.lease_generation == lease_generation,
                PipelineJobModel.status == JobStatus.RUNNING.value,
                PipelineJobModel.lease_until > now,
            )
            .values(
                status=JobStatus.COMPLETED.value,
                completed_at=now,
                lease_until=None,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0

