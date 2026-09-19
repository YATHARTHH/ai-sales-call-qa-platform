"""API contract schemas for evaluation results, audit queues, and human reviews."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from packages.domain.evaluation import HumanReviewAction, RerunMode


class GroundedEvidenceContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str
    transcript_segment_id: str
    transcript_id: str
    speaker: str
    evidence_type: str
    start_ms: int
    end_ms: int
    expected_value: Any
    observed_value: Any
    transcript_excerpt: str
    ai_explanation: str
    comparison_source: str | None = None
    expected_value_source: str | None = None
    observed_value_source: str | None = None


class CheckResultContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    result_id: str
    check_id: str
    check_version_id: str
    is_critical: bool
    result: str
    confidence: float | None
    score_numeric: float | None
    reason_codes: list[str] = Field(default_factory=list)
    evidence: list[GroundedEvidenceContract] = Field(default_factory=list)


class GateDecisionContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision_id: str
    status: str
    policy_version: str
    decision_reason_code: str
    auto_submitted: bool
    reason_codes: list[str] = Field(default_factory=list)
    blocking_check_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    decided_at: str


class HumanReviewContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    review_id: str
    reviewer_id: str
    reviewer_role: str
    action: str
    reason_notes: str
    reviewed_at: str


class EvaluationLineageResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    sale_id: str
    tenant_id: str
    transcript_id: str
    checklist_version_id: str
    status: str
    input_snapshot_id: str | None = None
    input_snapshot_hash: str | None = None
    input_snapshot_json: dict[str, Any] | None = None
    provenance: dict[str, Any]
    execution_metadata: dict[str, Any]
    results: list[CheckResultContract]
    gate_decision: GateDecisionContract | None = None
    human_reviews: list[HumanReviewContract] = Field(default_factory=list)


class EvaluationQueueItemResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision_id: str
    sale_id: str
    evaluation_run_id: str
    tenant_id: str
    status: str
    decision_reason_code: str
    auto_submitted: bool
    reason_codes: list[str] = Field(default_factory=list)
    blocking_check_ids: list[str] = Field(default_factory=list)
    decided_at: str
    created_at: str


class HumanReviewRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: HumanReviewAction
    reason_notes: str = Field(..., min_length=10, description="Mandatory audit explanation for override or hold")
    reviewer_role: str = Field(default="qa_auditor")


class HumanReviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    review_id: str
    gate_decision_id: str
    action: str
    previous_gate_status: str
    new_gate_status: str
    sale_disposition: str
    reviewed_at: str


class RerunEvaluationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: RerunMode = Field(default=RerunMode.RE_EVALUATE_ONLY)
    reason: str = Field(..., min_length=5)
