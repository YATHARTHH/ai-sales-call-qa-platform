"""Durable background pipeline job models, retry policies, and lease tracking."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum


class JobStatus(StrEnum):
    """Execution status of an asynchronous pipeline task."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"  # Terminal failure: no further automated retry


class FailureCategory(StrEnum):
    """Categorization of failure types to determine retry behavior."""

    TRANSIENT = "TRANSIENT"  # Network blip, DB lock timeout (RETRY)
    RATE_LIMITED = "RATE_LIMITED"  # HTTP 429 backoff (RETRY)
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"  # HTTP 503 / downstream restart (RETRY)
    PERMANENT = "PERMANENT"  # Malformed file, unsupported codec (NO RETRY)
    INVALID_INPUT = "INVALID_INPUT"  # Schema validation failure (NO RETRY)
    POLICY_FAILURE = "POLICY_FAILURE"  # Business rule violation (NO RETRY)
    UNKNOWN = "UNKNOWN"  # Unclassified (LIMITED RETRY)


@dataclass
class RetryPolicy:
    """Configurable retry policy with exponential backoff and classification."""

    max_retries: int = 3
    base_backoff_seconds: float = 2.0
    backoff_factor: float = 2.0

    # Non-retryable failure classes
    NON_RETRYABLE: set[FailureCategory] = field(
        default_factory=lambda: {
            FailureCategory.PERMANENT,
            FailureCategory.INVALID_INPUT,
            FailureCategory.POLICY_FAILURE,
        }
    )

    def is_retryable(self, category: FailureCategory) -> bool:
        """Check if a failure category is inherently retryable."""
        return category not in self.NON_RETRYABLE

    def should_retry(self, category: FailureCategory, current_retries: int) -> bool:
        """Determine if a job should be rescheduled or dead-lettered."""
        if not self.is_retryable(category):
            return False
        return current_retries < self.max_retries

    def calculate_backoff(self, retry_count: int) -> float:
        """Calculate exponential backoff delay in seconds."""
        return self.base_backoff_seconds * (self.backoff_factor**retry_count)


@dataclass
class PipelineJob:
    """Durable job entity stored in PostgreSQL."""

    id: str
    recording_id: str
    stage: str
    status: JobStatus
    idempotency_key: str
    retry_count: int = 0
    max_retries: int = 3
    last_error: str | None = None
    failure_category: FailureCategory | None = None
    worker_id: str | None = None
    heartbeat_at: datetime | None = None
    lease_until: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        recording_id: str,
        stage: str,
        input_artifact_hash: str,
        processor_version: str,
        max_retries: int = 3,
    ) -> "PipelineJob":
        """Create a new job with a stage-specific idempotency key."""
        idempotency_key = cls.build_idempotency_key(
            recording_id=recording_id,
            stage=stage,
            input_artifact_hash=input_artifact_hash,
            processor_version=processor_version,
        )
        now = datetime.now(UTC)
        return cls(
            id=str(uuid.uuid4()),
            recording_id=recording_id,
            stage=stage,
            status=JobStatus.QUEUED,
            idempotency_key=idempotency_key,
            max_retries=max_retries,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def build_idempotency_key(
        recording_id: str, stage: str, input_artifact_hash: str, processor_version: str
    ) -> str:
        """Format: {recording_id}:{stage}:{input_artifact_hash}:{processor_version}"""
        return f"{recording_id}:{stage}:{input_artifact_hash}:{processor_version}"

    def acquire_lease(self, worker_id: str, lease_duration_seconds: int = 60) -> None:
        """Claim job lease by an active worker."""
        now = datetime.now(UTC)
        self.status = JobStatus.RUNNING
        self.worker_id = worker_id
        self.started_at = self.started_at or now
        self.heartbeat_at = now
        self.lease_until = now + timedelta(seconds=lease_duration_seconds)
        self.updated_at = now

    def update_heartbeat(self, lease_duration_seconds: int = 60) -> None:
        """Refresh lease heartbeat while worker is processing."""
        now = datetime.now(UTC)
        self.heartbeat_at = now
        self.lease_until = now + timedelta(seconds=lease_duration_seconds)
        self.updated_at = now

    def mark_completed(self) -> None:
        """Mark job successfully completed."""
        now = datetime.now(UTC)
        self.status = JobStatus.COMPLETED
        self.completed_at = now
        self.lease_until = None
        self.updated_at = now

    def mark_failed(
        self,
        error_message: str,
        category: FailureCategory,
        policy: RetryPolicy | None = None,
    ) -> None:
        """Process job failure, transitioning to QUEUED (retry) or DEAD_LETTER."""
        active_policy = policy or RetryPolicy(max_retries=self.max_retries)
        self.last_error = error_message
        self.failure_category = category
        self.lease_until = None
        now = datetime.now(UTC)
        self.updated_at = now

        if active_policy.should_retry(category, self.retry_count):
            self.retry_count += 1
            self.status = JobStatus.QUEUED
        else:
            self.status = JobStatus.DEAD_LETTER

    def is_lease_expired(self, now: datetime | None = None) -> bool:
        """Check if worker heartbeat or lease timestamp has elapsed."""
        if self.status != JobStatus.RUNNING or not self.lease_until:
            return False
        current_time = now or datetime.now(UTC)
        return current_time > self.lease_until
