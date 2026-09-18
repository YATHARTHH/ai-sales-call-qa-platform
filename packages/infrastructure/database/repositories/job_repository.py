"""SQLAlchemy implementation of JobRepositoryPort."""

import asyncio

from sqlalchemy import select
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
            started_at=model.started_at,
            completed_at=model.completed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def get_by_id(self, job_id: str) -> PipelineJob | None:
        stmt = select(PipelineJobModel).where(PipelineJobModel.id == job_id)
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def get_by_idempotency_key(self, idempotency_key: str) -> PipelineJob | None:
        stmt = select(PipelineJobModel).where(PipelineJobModel.idempotency_key == idempotency_key)
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
