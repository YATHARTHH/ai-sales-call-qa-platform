"""SQLAlchemy models for evaluation runs, check results, evidence, gates, reviews, and audit events."""

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
    status: Mapped[str] = mapped_column(String(32), default="COMPLETED", nullable=False)

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
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    score_numeric: Mapped[float] = mapped_column(Float, nullable=False)
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
            "confidence >= 0.0 AND confidence <= 1.0", name="ck_eval_result_confidence"
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
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    observed_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    transcript_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    ai_explanation: Mapped[str] = mapped_column(Text, default="", nullable=False)
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
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_notes: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    gate_decision: Mapped[GateDecisionModel] = relationship(back_populates="human_reviews")
    reviewer: Mapped["AgentModel"] = relationship()


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
