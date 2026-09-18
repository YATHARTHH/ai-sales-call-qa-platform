"""Unit tests for lease-generation fencing and atomic lease acquisition."""

from datetime import UTC, datetime, timedelta

import pytest

from packages.domain.jobs import JobStatus
from packages.infrastructure.database.models.jobs import PipelineJobModel
from packages.infrastructure.database.repositories.job_repository import (
    SqlAlchemyJobRepository,
)


@pytest.mark.asyncio
async def test_atomic_lease_claim_increments_generation(test_db_session):
    """claim_job_lease_atomic must atomically increment lease_generation in PostgreSQL."""
    repo = SqlAlchemyJobRepository(test_db_session)
    now = datetime.now(UTC)

    # Insert initial queued job with lease_generation=0
    job_model = PipelineJobModel(
        id="job-lease-1",
        recording_id="rec-1",
        stage="TRANSCRIBING",
        status=JobStatus.QUEUED.value,
        idempotency_key="key-lease-1",
        lease_generation=0,
        created_at=now,
        updated_at=now,
    )
    test_db_session.add(job_model)
    await test_db_session.flush()

    # Claim lease by worker 1
    claimed_1 = await repo.claim_job_lease_atomic("job-lease-1", "worker-A", lease_duration_seconds=60)
    assert claimed_1 is not None
    assert claimed_1.worker_id == "worker-A"
    assert claimed_1.lease_generation == 1
    assert claimed_1.status == JobStatus.RUNNING

    # Claim lease again by worker 2 (e.g. after recovery or timeout)
    claimed_2 = await repo.claim_job_lease_atomic("job-lease-1", "worker-B", lease_duration_seconds=60)
    assert claimed_2 is not None
    assert claimed_2.worker_id == "worker-B"
    assert claimed_2.lease_generation == 2
    assert claimed_2.status == JobStatus.RUNNING


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
