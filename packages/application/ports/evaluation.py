"""Evaluation port contract for AI and LLM evaluation engines."""

from abc import ABC, abstractmethod
from typing import Any


class EvaluationPort(ABC):
    """Abstract interface for AI/LLM check evaluation providers."""

    @abstractmethod
    async def evaluate(
        self,
        check_code: str,
        transcript_segment: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Evaluate a specific compliance check against a transcript segment."""

    @abstractmethod
    def model_info(self) -> dict[str, str]:
        """Return provider and model version identity."""
