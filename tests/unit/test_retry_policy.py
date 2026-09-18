"""Tests for FailureCategory retry classification and DEAD_LETTER transitions."""

from packages.domain.jobs import FailureCategory, JobStatus, PipelineJob, RetryPolicy


def test_retry_classification():
    """Transient failures allow retry; permanent and invalid input failures are rejected."""
    policy = RetryPolicy(max_retries=3)

    # Retryable
    assert policy.should_retry(FailureCategory.TRANSIENT, current_retries=0) is True
    assert policy.should_retry(FailureCategory.RATE_LIMITED, current_retries=1) is True
    assert policy.should_retry(FailureCategory.PROVIDER_UNAVAILABLE, current_retries=2) is True

    # Non-retryable
    assert policy.should_retry(FailureCategory.PERMANENT, current_retries=0) is False
    assert policy.should_retry(FailureCategory.INVALID_INPUT, current_retries=0) is False
    assert policy.should_retry(FailureCategory.POLICY_FAILURE, current_retries=0) is False


def test_terminal_dead_letter_transition():
    """When retries exceed max_retries or failure is permanent, job transitions to DEAD_LETTER."""
    policy = RetryPolicy(max_retries=2)
    job = PipelineJob.create("rec-100", "transcription", "hash123", "whisper-v1", max_retries=2)

    # 1. First transient failure -> resets to QUEUED with retry_count=1
    job.mark_failed("Network timeout", FailureCategory.TRANSIENT, policy=policy)
    assert job.status == JobStatus.QUEUED
    assert job.retry_count == 1

    # 2. Second transient failure -> resets to QUEUED with retry_count=2
    job.mark_failed("Network timeout again", FailureCategory.TRANSIENT, policy=policy)
    assert job.status == JobStatus.QUEUED
    assert job.retry_count == 2

    # 3. Third failure (exceeds max_retries=2) -> transitions to DEAD_LETTER
    job.mark_failed("Network timeout final", FailureCategory.TRANSIENT, policy=policy)
    assert job.status == JobStatus.DEAD_LETTER

    # 4. Immediate DEAD_LETTER on non-retryable error
    fresh_job = PipelineJob.create("rec-200", "transcription", "hash456", "whisper-v1")
    fresh_job.mark_failed("Corrupted audio header", FailureCategory.PERMANENT, policy=policy)
    assert fresh_job.status == JobStatus.DEAD_LETTER
