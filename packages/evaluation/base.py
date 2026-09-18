"""Base check evaluator contract and finding definitions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from packages.domain.provenance import AIProvenance


@dataclass
class EvaluationFinding:
    """Standardized finding proposed by an evaluator."""

    check_code: str
    result: str  # "PASS", "FAIL", "AMBIGUOUS"
    confidence: float
    expected_value: Any
    observed_value: Any
    transcript_span: str
    audio_timestamp_ms: int
    provenance: AIProvenance
    details: str = ""


class BaseCheckEvaluator(ABC):
    """Abstract Strategy interface for all check evaluators (Verbatim, Factual, Behaviour)."""

    @abstractmethod
    async def evaluate(
        self,
        transcript_data: dict[str, Any],
        check_config: dict[str, Any],
        crm_fields: dict[str, Any] | None = None,
    ) -> EvaluationFinding:
        """Evaluate the check against transcript and CRM state."""
