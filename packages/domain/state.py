"""State machine definitions and transition policy validation."""

from enum import StrEnum
from typing import ClassVar

from packages.domain.exceptions import StateTransitionError


class PipelineStatus(StrEnum):
    """Operational lifecycle state of an ingested sales recording."""

    RECEIVED = "RECEIVED"
    INGESTING = "INGESTING"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSCRIBED = "TRANSCRIBED"
    EVALUATING = "EVALUATING"
    EVALUATED = "EVALUATED"
    FAILED = "FAILED"


class GateStatus(StrEnum):
    """Business compliance outcome for a sales lead."""

    PENDING = "PENDING"
    PASSED = "PASSED"
    HELD = "HELD"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CANCELLED = "CANCELLED"


class StateTransitionPolicy:
    """Enforces strict, auditable state machine transitions.

    Prevents illegal jumps (e.g. RECEIVED -> EVALUATED, or HELD -> PASSED without human review).
    """

    # Allowed operational pipeline transitions
    PIPELINE_TRANSITIONS: ClassVar[dict[PipelineStatus, set[PipelineStatus]]] = {
        PipelineStatus.RECEIVED: {PipelineStatus.INGESTING, PipelineStatus.FAILED},
        PipelineStatus.INGESTING: {PipelineStatus.TRANSCRIBING, PipelineStatus.FAILED},
        PipelineStatus.TRANSCRIBING: {PipelineStatus.TRANSCRIBED, PipelineStatus.FAILED},
        PipelineStatus.TRANSCRIBED: {PipelineStatus.EVALUATING, PipelineStatus.FAILED},
        PipelineStatus.EVALUATING: {PipelineStatus.EVALUATED, PipelineStatus.FAILED},
        # Recovery/Retry allows FAILED to re-enter INGESTING or TRANSCRIBING
        PipelineStatus.FAILED: {PipelineStatus.INGESTING, PipelineStatus.TRANSCRIBING, PipelineStatus.EVALUATING},
        PipelineStatus.EVALUATED: set(),  # Terminal pipeline state
    }

    # Allowed business QA gate transitions
    GATE_TRANSITIONS: ClassVar[dict[GateStatus, set[GateStatus]]] = {
        GateStatus.PENDING: {
            GateStatus.PASSED,
            GateStatus.HELD,
            GateStatus.REVIEW_REQUIRED,
            GateStatus.CANCELLED,
        },
        GateStatus.HELD: {
            GateStatus.PASSED,  # Only permitted after Team Lead override/resolution
            GateStatus.CANCELLED,
            GateStatus.REVIEW_REQUIRED,
        },
        GateStatus.REVIEW_REQUIRED: {
            GateStatus.PASSED,
            GateStatus.HELD,
            GateStatus.CANCELLED,
        },
        GateStatus.PASSED: set(),  # Terminal clean state
        GateStatus.CANCELLED: set(),  # Terminal cancelled state
    }

    @classmethod
    def validate_pipeline_transition(
        cls, current: PipelineStatus, target: PipelineStatus
    ) -> None:
        """Validate if the pipeline transition is allowed."""
        if current == target:
            return

        allowed = cls.PIPELINE_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise StateTransitionError(
                current.value, target.value, context="PipelineStatus"
            )

    @classmethod
    def validate_gate_transition(
        cls, current: GateStatus, target: GateStatus
    ) -> None:
        """Validate if the QA gate transition is allowed."""
        if current == target:
            return

        allowed = cls.GATE_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise StateTransitionError(
                current.value, target.value, context="GateStatus"
            )
