"""Base check evaluator interfaces, execution context, and result structures."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from packages.application.services.check_resolver import ResolvedCheck
from packages.domain.evaluation import (
    CheckExecutionResult,
    EvaluationInputSnapshot,
)
from packages.domain.transcript import TranscriptSegment


@dataclass(frozen=True)
class EvaluatorContext:
    """Read-only execution context supplied to each check evaluator."""

    snapshot: EvaluationInputSnapshot
    segments: Sequence[TranscriptSegment]
    sale_data: dict[str, Any] = field(default_factory=dict)
    lead_data: dict[str, Any] = field(default_factory=dict)
    speech_behavior: Any | None = None


class BaseCheckEvaluator(ABC):
    """Abstract Strategy interface for all check evaluators (Verbatim, Factual, Behaviour)."""

    @abstractmethod
    def can_evaluate(self, check: ResolvedCheck) -> bool:
        """Determines if this evaluator can execute the specified check."""

    @abstractmethod
    def evaluate(
        self,
        check: ResolvedCheck,
        context: EvaluatorContext,
    ) -> CheckExecutionResult:
        """Executes the check and returns structured outcome, score, confidence, and evidence."""
