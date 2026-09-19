"""Port for second-opinion adjudication of checks the deterministic evaluators could not settle.

Only findings the engine already marked AMBIGUOUS are sent here. The adjudicator proposes; the
deterministic policy gate still decides, and the policy never lets a proposal loosen a critical
outcome unless an operator explicitly opts in. Everything the adjudicator returns is recorded as
evidence with its model and prompt version so a decision can be defended in an audit.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum


class AdjudicationVerdictType(StrEnum):
    SATISFIED = "SATISFIED"
    NOT_SATISFIED = "NOT_SATISFIED"
    CANNOT_DETERMINE = "CANNOT_DETERMINE"


@dataclass(frozen=True)
class AdjudicationSegment:
    """One candidate transcript line the adjudicator may cite."""

    segment_id: str
    speaker: str
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class AdjudicationRequest:
    """Everything the adjudicator is allowed to see about one unresolved check."""

    check_code: str
    check_name: str
    requirement: str
    expected_value: str | None
    observed_value: str | None
    engine_outcome: str
    engine_confidence: float | None
    engine_reason_codes: list[str] = field(default_factory=list)
    segments: list[AdjudicationSegment] = field(default_factory=list)


@dataclass(frozen=True)
class AdjudicationVerdict:
    """A proposal, not a decision."""

    verdict: AdjudicationVerdictType
    confidence: float
    rationale: str
    supporting_segment_id: str | None = None
    provider: str = "none"
    model: str = "none"
    model_version: str = "none"
    prompt_version: str = "none"

    @classmethod
    def undetermined(cls, rationale: str) -> "AdjudicationVerdict":
        return cls(
            verdict=AdjudicationVerdictType.CANNOT_DETERMINE,
            confidence=0.0,
            rationale=rationale,
        )


class AdjudicatorPort(ABC):
    """Proposes a resolution for a check the deterministic evaluators left ambiguous."""

    @abstractmethod
    def adjudicate(self, request: AdjudicationRequest) -> AdjudicationVerdict:
        """Return a proposed verdict. Must never raise; return CANNOT_DETERMINE instead."""

    @abstractmethod
    def provider_name(self) -> str:
        """Identifier recorded in evidence provenance."""


class NullAdjudicator(AdjudicatorPort):
    """Default adjudicator: declines every case, leaving ambiguity for a human."""

    def adjudicate(self, request: AdjudicationRequest) -> AdjudicationVerdict:
        return AdjudicationVerdict.undetermined("No adjudicator configured.")

    def provider_name(self) -> str:
        return "none"
