"""AI provenance lineage and operational execution telemetry models."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AIProvenance:
    """Identity and configuration lineage of an AI model execution.

    Invariants:
    - Fully identifies which exact models, prompt versions, check configurations,
      and policy rules produced a specific evaluation.
    - Enables 100% reproducible auditing across time.
    """

    provider: str
    model: str
    model_version: str
    prompt_version: str
    check_version: str
    policy_version: str
    pipeline_git_sha: str = ""
    temperature: float = 0.0
    seed: int | None = None


@dataclass
class AIExecutionMetadata:
    """Runtime telemetry and resource metrics for an AI model execution."""

    started_at: datetime
    completed_at: datetime
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0

    @classmethod
    def create(
        cls,
        started_at: datetime,
        completed_at: datetime,
        input_tokens: int = 0,
        output_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
    ) -> "AIExecutionMetadata":
        """Compute duration latency in milliseconds automatically."""
        duration = (completed_at - started_at).total_seconds() * 1000.0
        return cls(
            started_at=started_at,
            completed_at=completed_at,
            latency_ms=round(duration, 2),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost_usd,
        )
