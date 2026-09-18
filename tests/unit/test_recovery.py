"""Tests for worker lease heartbeat and crash recovery logic."""

from datetime import UTC, datetime, timedelta

from packages.domain.jobs import FailureCategory, JobStatus, PipelineJob, RetryPolicy


def test_lease_expiration_detection():
    """A job in RUNNING state must detect when its lease has expired."""
    job = PipelineJob.create("rec-999", "evaluation", "hash-xyz", "eval-v1")
    job.acquire_lease("worker-pid-1234", lease_duration_seconds=10)

    assert job.status == JobStatus.RUNNING
    assert job.is_lease_expired() is False

    # Simulate time passing beyond lease_until
    future_time = datetime.now(UTC) + timedelta(seconds=20)
    assert job.is_lease_expired(now=future_time) is True


def test_stale_job_recovery_transitions():
    """Expired running job reclaims lease into QUEUED or DEAD_LETTER when retries exhausted."""
    policy = RetryPolicy(max_retries=2)
    job = PipelineJob.create("rec-999", "evaluation", "hash-xyz", "eval-v1", max_retries=2)
    job.acquire_lease("worker-pid-1234", lease_duration_seconds=5)

    # Job crashed while RUNNING; mark failure via recovery
    job.mark_failed("Lease expired; worker died", FailureCategory.TRANSIENT, policy=policy)
    assert job.status == JobStatus.QUEUED
    assert job.retry_count == 1

    # Second crash
    job.acquire_lease("worker-pid-5678", lease_duration_seconds=5)
    job.mark_failed("Lease expired second time", FailureCategory.TRANSIENT, policy=policy)
    assert job.status == JobStatus.QUEUED
    assert job.retry_count == 2

    # Third crash -> exceeds max_retries -> DEAD_LETTER
    job.acquire_lease("worker-pid-9999", lease_duration_seconds=5)
    job.mark_failed("Lease expired final time", FailureCategory.TRANSIENT, policy=policy)
    assert job.status == JobStatus.DEAD_LETTER
