"""SalesCall QA Domain Layer.

Zero external dependencies allowed (no SQLAlchemy, FastAPI, Redis, or Boto3).
Contains pure business logic, domain entities, state machines, and exceptions.
"""

from packages.domain.artifacts import Artifact
from packages.domain.audit import ActorType, AuditEvent
from packages.domain.check_library import (
    CheckDefinition,
    CheckType,
    CheckVersion,
    CheckVersionResolver,
    VersionResolutionError,
)
from packages.domain.evaluation import (
    EvaluationResult,
    EvaluationResultStatus,
    EvaluationRun,
    Evidence,
    GateDecision,
    HumanReview,
    HumanReviewAction,
)
from packages.domain.exceptions import (
    ArtifactImmutableError,
    DomainError,
    EntityNotFoundError,
    IdempotencyConflictError,
    StateTransitionError,
)
from packages.domain.jobs import FailureCategory, JobStatus, PipelineJob, RetryPolicy
from packages.domain.provenance import AIExecutionMetadata, AIProvenance
from packages.domain.retail import (
    Agent,
    Campaign,
    EnergyProductDetails,
    FuelType,
    Lead,
    Retailer,
    Sale,
    SaleStatus,
)
from packages.domain.state import GateStatus, PipelineStatus, StateTransitionPolicy
from packages.domain.transcript import (
    Recording,
    SpeakerType,
    Transcript,
    TranscriptSegment,
)

__all__ = [
    # Artifacts & State
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
    # Retail
    "Retailer",
    "Campaign",
    "Agent",
    "Lead",
    "Sale",
    "SaleStatus",
    "FuelType",
    "EnergyProductDetails",
    # Transcript
    "Recording",
    "Transcript",
    "TranscriptSegment",
    "SpeakerType",
    # Check Library
    "CheckType",
    "CheckDefinition",
    "CheckVersion",
    "CheckVersionResolver",
    "VersionResolutionError",
    # Evaluation
    "EvaluationRun",
    "EvaluationResult",
    "EvaluationResultStatus",
    "Evidence",
    "GateDecision",
    "HumanReview",
    "HumanReviewAction",
    # Audit
    "ActorType",
    "AuditEvent",
]
