"""SQLAlchemy models for evaluation runs, check results, evidence, gates, reviews, outbox, and audit events."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from packages.infrastructure.database.base import Base

if TYPE_CHECKING:
    from packages.infrastructure.database.models.checks import CheckVersionModel
    from packages.infrastructure.database.models.sales import AgentModel, SaleModel
    from packages.infrastructure.database.models.transcripts import (
        TranscriptModel,
        TranscriptSegmentModel,
    )


class EvaluationRunModel(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sale_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sales.id"), nullable=False, index=True
    )
    transcript_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("transcripts.id"), nullable=False, index=True
    )
    checklist_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="SUCCEEDED", nullable=False)
    tenant_id: Mapped[str] = mapped_column(
        String(64), default="default-tenant", nullable=False, index=True
    )

    # Immutable Snapshot fields
    input_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Provenance fields (AI Lineage)
    model_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_template_version: Mapped[str] = mapped_column(String(64), nullable=False)
    pipeline_git_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Execution telemetry
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    sale: Mapped["SaleModel"] = relationship()
    transcript: Mapped["TranscriptModel"] = relationship()
    results: Mapped[list["EvaluationResultModel"]] = relationship(
        back_populates="evaluation_run", cascade="all, delete-orphan"
    )
    gate_decision: Mapped["GateDecisionModel | None"] = relationship(
        back_populates="evaluation_run", uselist=False
    )

    __table_args__ = (
        Index("ix_evaluation_runs_sale_transcript", "sale_id", "transcript_id"),
        Index(
            "ix_evaluation_runs_lineage",
            "sale_id",
            "transcript_id",
            "checklist_version_id",
            "policy_version",
        ),
        Index("ix_evaluation_runs_tenant", "tenant_id", "created_at"),
    )


class EvaluationResultModel(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evaluation_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    check_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("check_versions.id"), nullable=False, index=True
    )
    check_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    evaluation_run: Mapped[EvaluationRunModel] = relationship(back_populates="results")
    check_version: Mapped["CheckVersionModel"] = relationship()
    evidence: Mapped[list["EvidenceModel"]] = relationship(
        back_populates="evaluation_result", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("evaluation_run_id", "check_version_id", name="uq_run_check_version"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_eval_result_confidence",
        ),
    )


class EvidenceModel(Base):
    __tablename__ = "evaluation_evidences"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evaluation_result_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("evaluation_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transcript_segment_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("transcript_segments.id"), nullable=False, index=True
    )
    transcript_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    speaker: Mapped[str] = mapped_column(String(32), default="AGENT", nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(32), default="SUPPORTING", nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    observed_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    transcript_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    ai_explanation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    comparison_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_value_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_value_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    evaluation_result: Mapped[EvaluationResultModel] = relationship(back_populates="evidence")
    transcript_segment: Mapped["TranscriptSegmentModel"] = relationship()

    __table_args__ = (
        CheckConstraint("start_ms >= 0 AND end_ms >= start_ms", name="ck_evidence_timestamps"),
    )


class GateDecisionModel(Base):
    __tablename__ = "gate_decisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sale_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sales.id"), nullable=False, index=True
    )
    evaluation_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("evaluation_runs.id"), nullable=False, unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    auto_submitted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    blocking_check_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    evaluation_run: Mapped[EvaluationRunModel] = relationship(back_populates="gate_decision")
    human_reviews: Mapped[list["HumanReviewModel"]] = relationship(
        back_populates="gate_decision", cascade="all, delete-orphan"
    )


class HumanReviewModel(Base):
    __tablename__ = "human_reviews"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    gate_decision_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("gate_decisions.id"), nullable=False, index=True
    )
    reviewer_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("agents.id"), nullable=False, index=True
    )
    reviewer_role: Mapped[str] = mapped_column(String(32), default="qa_auditor", nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_notes: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    gate_decision: Mapped[GateDecisionModel] = relationship(back_populates="human_reviews")
    reviewer: Mapped["AgentModel"] = relationship()


class OutboxEventModel(Base):
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_schema_version: Mapped[str] = mapped_column(String(16), default="v1", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_outbox_unpublished", "published_at", "locked_until", "next_attempt_at"),
    )


class AuditEventModel(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_audit_entity_lookup", "entity_type", "entity_id", "created_at"),
        Index("ix_audit_actor_lookup", "actor_id", "created_at"),
    )
