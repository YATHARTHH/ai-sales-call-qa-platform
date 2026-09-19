"""Unit tests for lease-generation fencing and atomic lease acquisition."""

from datetime import UTC, datetime, timedelta

import pytest

from packages.domain.jobs import JobStatus
from packages.infrastructure.database.models.jobs import PipelineJobModel
from packages.infrastructure.database.repositories.job_repository import (
    SqlAlchemyJobRepository,
)


async def _insert_job(
    session,
    job_id: str,
    status: JobStatus = JobStatus.QUEUED,
    lease_until=None,
    lease_generation: int = 0,
) -> None:
    now = datetime.now(UTC)
    session.add(
        PipelineJobModel(
            id=job_id,
            recording_id="rec-1",
            stage="TRANSCRIBING",
            status=status.value,
            idempotency_key=f"key-{job_id}",
            lease_generation=lease_generation,
            lease_until=lease_until,
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_atomic_lease_claim_increments_generation(test_db_session):
    """A queued job is claimable and the claim atomically increments lease_generation."""
    repo = SqlAlchemyJobRepository(test_db_session)
    await _insert_job(test_db_session, "job-lease-1")

    claimed = await repo.claim_job_lease_atomic("job-lease-1", "worker-A", lease_duration_seconds=60)

    assert claimed is not None
    assert claimed.worker_id == "worker-A"
    assert claimed.lease_generation == 1
    assert claimed.status == JobStatus.RUNNING


@pytest.mark.asyncio
async def test_live_lease_cannot_be_stolen_by_a_second_worker(test_db_session):
    """Two workers must never hold the same job at once — that is what a lease is for."""
    repo = SqlAlchemyJobRepository(test_db_session)
    await _insert_job(test_db_session, "job-lease-live")

    first = await repo.claim_job_lease_atomic("job-lease-live", "worker-A", lease_duration_seconds=60)
    second = await repo.claim_job_lease_atomic("job-lease-live", "worker-B", lease_duration_seconds=60)

    assert first is not None
    assert second is None


@pytest.mark.asyncio
async def test_expired_lease_is_recoverable_by_another_worker(test_db_session):
    """When a worker dies its lease expires and another may take over, fencing the first out."""
    repo = SqlAlchemyJobRepository(test_db_session)
    await _insert_job(
        test_db_session,
        "job-lease-expired",
        status=JobStatus.RUNNING,
        lease_until=datetime.now(UTC) - timedelta(seconds=5),
        lease_generation=1,
    )

    recovered = await repo.claim_job_lease_atomic(
        "job-lease-expired", "worker-B", lease_duration_seconds=60
    )

    assert recovered is not None
    assert recovered.worker_id == "worker-B"
    # The generation moves on, so the dead worker's late completion is fenced out.
    assert recovered.lease_generation == 2


@pytest.mark.asyncio
async def test_completed_job_is_never_reclaimed(test_db_session):
    """A redelivered message for a finished job must not reprocess it.

    Without this guard an at-least-once queue would write a second evaluation run, a second gate
    decision, and a second CRM event for a sale that was already decided.
    """
    repo = SqlAlchemyJobRepository(test_db_session)
    await _insert_job(test_db_session, "job-done", status=JobStatus.COMPLETED)

    assert await repo.claim_job_lease_atomic("job-done", "worker-A") is None


@pytest.mark.asyncio
async def test_dead_letter_job_is_never_reclaimed(test_db_session):
    repo = SqlAlchemyJobRepository(test_db_session)
    await _insert_job(test_db_session, "job-dead", status=JobStatus.DEAD_LETTER)

    assert await repo.claim_job_lease_atomic("job-dead", "worker-A") is None


@pytest.mark.asyncio
async def test_complete_job_with_lease_fence_success(test_db_session):
    """Job completes when worker_id, lease_generation, and unexpired lease match."""
    repo = SqlAlchemyJobRepository(test_db_session)
    now = datetime.now(UTC)

    job_model = PipelineJobModel(
        id="job-fence-ok",
        recording_id="rec-1",
        stage="TRANSCRIBING",
        status=JobStatus.RUNNING.value,
        worker_id="worker-A",
        lease_generation=3,
        lease_until=now + timedelta(seconds=120),
        idempotency_key="key-fence-ok",
        created_at=now,
        updated_at=now,
    )
    test_db_session.add(job_model)
    await test_db_session.flush()

    fenced = await repo.complete_job_with_lease_fence(
        job_id="job-fence-ok",
        worker_id="worker-A",
        lease_generation=3,
    )
    assert fenced is True

    updated = await repo.get_by_id("job-fence-ok")
    assert updated is not None
    assert updated.status == JobStatus.COMPLETED
    assert updated.lease_until is None


@pytest.mark.asyncio
async def test_complete_job_rejected_on_stale_generation(test_db_session):
    """A stale worker owning generation 3 cannot complete a job assigned to generation 4."""
    repo = SqlAlchemyJobRepository(test_db_session)
    now = datetime.now(UTC)

    # Job is currently owned by worker-B at generation 4
    job_model = PipelineJobModel(
        id="job-stale-gen",
        recording_id="rec-1",
        stage="TRANSCRIBING",
        status=JobStatus.RUNNING.value,
        worker_id="worker-B",
        lease_generation=4,
        lease_until=now + timedelta(seconds=120),
        idempotency_key="key-stale-gen",
        created_at=now,
        updated_at=now,
    )
    test_db_session.add(job_model)
    await test_db_session.flush()

    # Stale worker-A tries to commit with its old generation 3
    fenced = await repo.complete_job_with_lease_fence(
        job_id="job-stale-gen",
        worker_id="worker-A",
        lease_generation=3,
    )
    assert fenced is False

    # Job remains intact with worker-B
    current = await repo.get_by_id("job-stale-gen")
    assert current.status == JobStatus.RUNNING
    assert current.worker_id == "worker-B"
    assert current.lease_generation == 4


@pytest.mark.asyncio
async def test_complete_job_rejected_on_expired_lease(test_db_session):
    """Worker cannot complete job if its lease has expired (lease_until < now)."""
    repo = SqlAlchemyJobRepository(test_db_session)
    now = datetime.now(UTC)

    # Job lease expired 10 seconds ago
    job_model = PipelineJobModel(
        id="job-expired-lease",
        recording_id="rec-1",
        stage="TRANSCRIBING",
        status=JobStatus.RUNNING.value,
        worker_id="worker-A",
        lease_generation=1,
        lease_until=now - timedelta(seconds=10),
        idempotency_key="key-expired-lease",
        created_at=now,
        updated_at=now,
    )
    test_db_session.add(job_model)
    await test_db_session.flush()

    fenced = await repo.complete_job_with_lease_fence(
        job_id="job-expired-lease",
        worker_id="worker-A",
        lease_generation=1,
    )
    assert fenced is False
