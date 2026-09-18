"""Domain models for evaluation runs, results, grounded evidence, and gate decisions."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from packages.domain.provenance import AIExecutionMetadata, AIProvenance
from packages.domain.state import GateStatus


class EvaluationResultStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    AMBIGUOUS = "AMBIGUOUS"


class HumanReviewAction(StrEnum):
    OVERRIDE_TO_PASS = "OVERRIDE_TO_PASS"
    CONFIRM_HOLD = "CONFIRM_HOLD"
    CANCEL_SALE = "CANCEL_SALE"


@dataclass(frozen=True)
class EvaluationRun:
    """Represents a discrete evaluation execution across a transcript."""

    id: str
    sale_id: str
    transcript_id: str
    checklist_version_id: str
    provenance: AIProvenance
    status: str = "COMPLETED"
    execution_metadata: AIExecutionMetadata | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        sale_id: str,
        transcript_id: str,
        checklist_version_id: str,
        provenance: AIProvenance,
        execution_metadata: AIExecutionMetadata | None = None,
        run_id: str | None = None,
    ) -> "EvaluationRun":
        return cls(
            id=run_id or str(uuid.uuid4()),
            sale_id=sale_id,
            transcript_id=transcript_id,
            checklist_version_id=checklist_version_id,
            provenance=provenance,
            execution_metadata=execution_metadata,
            created_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class EvaluationResult:
    """Outcome for a single check evaluated in an EvaluationRun."""

    id: str
    evaluation_run_id: str
    check_version_id: str
    result: EvaluationResultStatus
    confidence: float
    score_numeric: float
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        evaluation_run_id: str,
        check_version_id: str,
        result: EvaluationResultStatus,
        confidence: float,
        score_numeric: float,
        result_id: str | None = None,
    ) -> "EvaluationResult":
        return cls(
            id=result_id or str(uuid.uuid4()),
            evaluation_run_id=evaluation_run_id,
            check_version_id=check_version_id,
            result=result,
            confidence=round(confidence, 4),
            score_numeric=score_numeric,
            created_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class Evidence:
    """Ground-truth audio-transcript evidence verifying an evaluation outcome."""

    id: str
    evaluation_result_id: str
    transcript_segment_id: str
    start_ms: int
    end_ms: int
    expected_value: Any
    observed_value: Any
    transcript_excerpt: str  # Display snapshot
    ai_explanation: str  # Model-generated explanation (explicitly separated from factual evidence)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        evaluation_result_id: str,
        transcript_segment_id: str,
        start_ms: int,
        end_ms: int,
        expected_value: Any,
        observed_value: Any,
        transcript_excerpt: str,
        ai_explanation: str = "",
        evidence_id: str | None = None,
    ) -> "Evidence":
        return cls(
            id=evidence_id or str(uuid.uuid4()),
            evaluation_result_id=evaluation_result_id,
            transcript_segment_id=transcript_segment_id,
            start_ms=start_ms,
            end_ms=end_ms,
            expected_value=expected_value,
            observed_value=observed_value,
            transcript_excerpt=transcript_excerpt.strip(),
            ai_explanation=ai_explanation.strip(),
            created_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class GateDecision:
    """Deterministic policy gate outcome deciding whether a sale auto-ships or is held."""

    id: str
    sale_id: str
    evaluation_run_id: str
    status: GateStatus
    policy_version: str
    decision_reason_code: str
    auto_submitted: bool = False
    decided_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        sale_id: str,
        evaluation_run_id: str,
        status: GateStatus,
        policy_version: str,
        decision_reason_code: str,
        auto_submitted: bool = False,
        decision_id: str | None = None,
    ) -> "GateDecision":
        return cls(
            id=decision_id or str(uuid.uuid4()),
            sale_id=sale_id,
            evaluation_run_id=evaluation_run_id,
            status=status,
            policy_version=policy_version,
            decision_reason_code=decision_reason_code,
            auto_submitted=auto_submitted,
            decided_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class HumanReview:
    """Immutable audit record of a Team Lead or QA human override."""

    id: str
    gate_decision_id: str
    reviewer_id: str
    action: HumanReviewAction
    reason_notes: str
    reviewed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        gate_decision_id: str,
        reviewer_id: str,
        action: HumanReviewAction,
        reason_notes: str,
        review_id: str | None = None,
    ) -> "HumanReview":
        return cls(
            id=review_id or str(uuid.uuid4()),
            gate_decision_id=gate_decision_id,
            reviewer_id=reviewer_id,
            action=action,
            reason_notes=reason_notes.strip(),
            reviewed_at=datetime.now(UTC),
        )
