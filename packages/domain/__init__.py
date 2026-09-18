"""SalesCall QA Domain Layer.

Zero external dependencies allowed (no SQLAlchemy, FastAPI, Redis, or Boto3).
Contains pure business logic, domain entities, state machines, and exceptions.
"""

from packages.domain.artifacts import Artifact
from packages.domain.exceptions import (
    ArtifactImmutableError,
    DomainError,
    EntityNotFoundError,
    IdempotencyConflictError,
    StateTransitionError,
)
from packages.domain.jobs import FailureCategory, JobStatus, PipelineJob, RetryPolicy
from packages.domain.provenance import AIExecutionMetadata, AIProvenance
from packages.domain.state import GateStatus, PipelineStatus, StateTransitionPolicy

__all__ = [
    "Artifact",
    "DomainError",
    "EntityNotFoundError",
    "StateTransitionError",
    "ArtifactImmutableError",
    "IdempotencyConflictError",
    "PipelineStatus",
    "GateStatus",
    "StateTransitionPolicy",
    "JobStatus",
    "FailureCategory",
    "RetryPolicy",
    "PipelineJob",
    "AIProvenance",
    "AIExecutionMetadata",
]
