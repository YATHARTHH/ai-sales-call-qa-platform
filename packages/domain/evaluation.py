"""Domain models for evaluation runs, results, grounded evidence, snapshots, and gate decisions."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from packages.domain.provenance import AIExecutionMetadata, AIProvenance
from packages.domain.state import GateStatus


class EvaluationRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    STALE = "STALE"


class CheckOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    AMBIGUOUS = "AMBIGUOUS"
    UNSUPPORTED = "UNSUPPORTED"
    NOT_EVALUABLE = "NOT_EVALUABLE"


# Backward compatibility alias
EvaluationResultStatus = CheckOutcome


class EvidenceType(StrEnum):
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"
    CONTEXT = "CONTEXT"


class GateReasonCode(StrEnum):
    TRANSCRIPT_INCOMPLETE = "TRANSCRIPT_INCOMPLETE"
    CRITICAL_CHECK_FAILED = "CRITICAL_CHECK_FAILED"
    CRITICAL_CHECK_EXECUTION_ERROR = "CRITICAL_CHECK_EXECUTION_ERROR"
    UNSUPPORTED_CRITICAL_CHECK = "UNSUPPORTED_CRITICAL_CHECK"
    LOW_CONFIDENCE_OR_AMBIGUOUS_FINDING = "LOW_CONFIDENCE_OR_AMBIGUOUS_FINDING"
    NO_SCOREABLE_CHECKS = "NO_SCOREABLE_CHECKS"
    NO_APPLICABLE_CHECKS = "NO_APPLICABLE_CHECKS"
    OVERALL_SCORE_BELOW_THRESHOLD = "OVERALL_SCORE_BELOW_THRESHOLD"
    MANUAL_REVIEW_REQUESTED = "MANUAL_REVIEW_REQUESTED"
    ALL_CRITICAL_CHECKS_PASSED = "ALL_CRITICAL_CHECKS_PASSED"


class HumanReviewAction(StrEnum):
    OVERRIDE_TO_PASS = "OVERRIDE_TO_PASS"
    CONFIRM_HOLD = "CONFIRM_HOLD"
    CANCEL_SALE = "CANCEL_SALE"


class RerunMode(StrEnum):
    RE_EVALUATE_ONLY = "RE_EVALUATE_ONLY"
    FULL_REPROCESSING = "FULL_REPROCESSING"


@dataclass(frozen=True)
class EvaluationInputSnapshot:
    """Immutable evaluation input snapshot capturing all factual inputs and configuration.

    Non-default required fields strictly precede defaulted fields.
    """

    # 1. Non-default required fields
    snapshot_id: str
    sale_id: str
    tenant_id: str
    transcript_id: str
    transcript_version_id: str
    transcript_content_hash: str
    audio_artifact_hash: str
    sale_snapshot: dict[str, Any]
    lead_snapshot: dict[str, Any]
    resolved_check_snapshots: tuple[dict[str, Any], ...]
    policy_version: str
    evaluator_config_hash: str
    applicability_version: str

    # 2. Defaulted fields
    snapshot_schema_version: str = "snapshot.v1"
    created_by: str = "system:worker"
    snapshot_content_hash_algorithm: str = "SHA-256"
    snapshot_content_hash: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        sale_id: str,
        tenant_id: str,
        transcript_id: str,
        transcript_version_id: str,
        transcript_content_hash: str,
        audio_artifact_hash: str,
        sale_snapshot: dict[str, Any],
        lead_snapshot: dict[str, Any],
        resolved_check_snapshots: list[dict[str, Any]] | tuple[dict[str, Any], ...],
        policy_version: str,
        evaluator_config_hash: str,
        applicability_version: str = "v1",
        snapshot_id: str | None = None,
        created_by: str = "system:worker",
    ) -> "EvaluationInputSnapshot":
        return cls(
            snapshot_id=snapshot_id or str(uuid.uuid4()),
            sale_id=sale_id,
            tenant_id=tenant_id,
            transcript_id=transcript_id,
            transcript_version_id=transcript_version_id,
            transcript_content_hash=transcript_content_hash,
            audio_artifact_hash=audio_artifact_hash,
            sale_snapshot=sale_snapshot,
            lead_snapshot=lead_snapshot,
            resolved_check_snapshots=tuple(resolved_check_snapshots),
            policy_version=policy_version,
            evaluator_config_hash=evaluator_config_hash,
            applicability_version=applicability_version,
            created_by=created_by,
        )


@dataclass(frozen=True)
class GroundedEvidence:
    """Evaluator output evidence before persistence."""

    transcript_segment_id: str
    transcript_id: str
    speaker: str
    evidence_type: EvidenceType
    start_ms: int
    end_ms: int
    expected_value: Any
    observed_value: Any
    transcript_excerpt: str
    ai_explanation: str = ""
    comparison_source: str | None = None
    expected_value_source: str | None = None
    observed_value_source: str | None = None


@dataclass(frozen=True)
class CheckExecutionResult:
    """Outcome for a single check evaluated by an Evaluator."""

    check_id: str
    check_version_id: str
    is_critical: bool
    outcome: CheckOutcome
    confidence: float | None
    score_numeric: float | None
    evidences: list[GroundedEvidence] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Evidence:
    """Ground-truth audio-transcript evidence verifying an evaluation outcome."""

    id: str
    evaluation_result_id: str
    transcript_segment_id: str
    transcript_id: str
    speaker: str
    evidence_type: EvidenceType
    start_ms: int
    end_ms: int
    expected_value: Any
    observed_value: Any
    transcript_excerpt: str
    ai_explanation: str = ""
    comparison_source: str | None = None
    expected_value_source: str | None = None
    observed_value_source: str | None = None
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
        transcript_id: str = "",
        speaker: str = "AGENT",
        evidence_type: EvidenceType = EvidenceType.SUPPORTING,
        comparison_source: str | None = None,
        expected_value_source: str | None = None,
        observed_value_source: str | None = None,
        evidence_id: str | None = None,
    ) -> "Evidence":
        return cls(
            id=evidence_id or str(uuid.uuid4()),
            evaluation_result_id=evaluation_result_id,
            transcript_segment_id=transcript_segment_id,
            transcript_id=transcript_id,
            speaker=speaker,
            evidence_type=evidence_type,
            start_ms=start_ms,
            end_ms=end_ms,
            expected_value=expected_value,
            observed_value=observed_value,
            transcript_excerpt=transcript_excerpt.strip(),
            ai_explanation=ai_explanation.strip(),
            comparison_source=comparison_source,
            expected_value_source=expected_value_source,
            observed_value_source=observed_value_source,
            created_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class EvaluationResult:
    """Outcome for a single check evaluated in an EvaluationRun."""

    id: str
    evaluation_run_id: str
    check_id: str
    check_version_id: str
    is_critical: bool
    result: CheckOutcome
    confidence: float | None
    score_numeric: float | None
    reason_codes: list[str] = field(default_factory=list)
    evidences: list[Evidence] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        evaluation_run_id: str,
        check_version_id: str,
        result: CheckOutcome,
        confidence: float | None,
        score_numeric: float | None,
        check_id: str = "",
        is_critical: bool = True,
        reason_codes: list[str] | None = None,
        evidences: list[Evidence] | None = None,
        result_id: str | None = None,
    ) -> "EvaluationResult":
        return cls(
            id=result_id or str(uuid.uuid4()),
            evaluation_run_id=evaluation_run_id,
            check_id=check_id or check_version_id,
            check_version_id=check_version_id,
            is_critical=is_critical,
            result=result,
            confidence=round(confidence, 4) if confidence is not None else None,
            score_numeric=score_numeric,
            reason_codes=reason_codes or [],
            evidences=evidences or [],
            created_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class EvaluationRun:
    """Represents a discrete evaluation execution across a transcript."""

    id: str
    sale_id: str
    tenant_id: str
    transcript_id: str
    checklist_version_id: str
    provenance: AIProvenance
    status: EvaluationRunStatus = EvaluationRunStatus.SUCCEEDED
    input_snapshot: EvaluationInputSnapshot | None = None
    input_snapshot_id: str | None = None
    input_snapshot_hash: str | None = None
    overall_score: float | None = None
    results: list[EvaluationResult] = field(default_factory=list)
    execution_metadata: AIExecutionMetadata | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        sale_id: str,
        transcript_id: str,
        checklist_version_id: str,
        provenance: AIProvenance,
        tenant_id: str = "default-tenant",
        status: EvaluationRunStatus = EvaluationRunStatus.RUNNING,
        input_snapshot: EvaluationInputSnapshot | None = None,
        overall_score: float | None = None,
        execution_metadata: AIExecutionMetadata | None = None,
        run_id: str | None = None,
    ) -> "EvaluationRun":
        return cls(
            id=run_id or str(uuid.uuid4()),
            sale_id=sale_id,
            tenant_id=tenant_id,
            transcript_id=transcript_id,
            checklist_version_id=checklist_version_id,
            provenance=provenance,
            status=status,
            input_snapshot=input_snapshot,
            input_snapshot_id=input_snapshot.snapshot_id if input_snapshot else None,
            input_snapshot_hash=input_snapshot.snapshot_content_hash if input_snapshot else None,
            overall_score=overall_score,
            execution_metadata=execution_metadata,
            created_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class GateDecision:
    """Deterministic policy gate outcome deciding whether a sale auto-ships or is held."""

    id: str
    sale_id: str
    evaluation_run_id: str
    status: GateStatus
    overall_score: float | None
    policy_version: str
    decision_reason_code: str
    auto_submitted: bool = False
    reason_codes: list[str] = field(default_factory=list)
    blocking_check_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    decided_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        sale_id: str,
        evaluation_run_id: str,
        status: GateStatus,
        policy_version: str,
        decision_reason_code: str,
        overall_score: float | None = None,
        auto_submitted: bool = False,
        reason_codes: list[str] | None = None,
        blocking_check_ids: list[str] | None = None,
        warnings: list[str] | None = None,
        decision_id: str | None = None,
    ) -> "GateDecision":
        return cls(
            id=decision_id or str(uuid.uuid4()),
            sale_id=sale_id,
            evaluation_run_id=evaluation_run_id,
            status=status,
            policy_version=policy_version,
            decision_reason_code=decision_reason_code,
            overall_score=overall_score,
            auto_submitted=auto_submitted,
            reason_codes=reason_codes or [],
            blocking_check_ids=blocking_check_ids or [],
            warnings=warnings or [],
            decided_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class HumanReview:
    """Immutable audit record of a Team Lead or QA human override."""

    id: str
    gate_decision_id: str
    reviewer_id: str
    reviewer_role: str
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
        reviewer_role: str = "qa_auditor",
        review_id: str | None = None,
    ) -> "HumanReview":
        return cls(
            id=review_id or str(uuid.uuid4()),
            gate_decision_id=gate_decision_id,
            reviewer_id=reviewer_id,
            reviewer_role=reviewer_role,
            action=action,
            reason_notes=reason_notes.strip(),
            reviewed_at=datetime.now(UTC),
        )
