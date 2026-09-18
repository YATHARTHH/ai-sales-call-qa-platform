"""Phase 1 domain schema: retailers, sales, transcripts, checks, evaluations, gate decisions, audit events.

Revision ID: 20260918_0002
Revises: 20260918_0001
Create Date: 2026-09-18 19:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260918_0002"
down_revision: str | None = "20260918_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. retailers
    op.create_table(
        "retailers",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("vertical", sa.String(length=64), server_default="ENERGY", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_retailers_code", "retailers", ["code"])

    # 2. campaigns
    op.create_table(
        "campaigns",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("channel", sa.String(length=64), server_default="INBOUND", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_campaigns_code", "campaigns", ["code"])

    # 3. agents
    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("staff_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=128), nullable=False),
        sa.Column("team_lead_id", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("staff_id"),
    )
    op.create_index("ix_agents_staff_id", "agents", ["staff_id"])
    op.create_index("ix_agents_email", "agents", ["email"])

    # 4. leads
    op.create_table(
        "leads",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("customer_name", sa.String(length=128), nullable=False),
        sa.Column("customer_email", sa.String(length=128), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("suburb", sa.String(length=64), server_default="", nullable=False),
        sa.Column("state", sa.String(length=32), server_default="", nullable=False),
        sa.Column("postcode", sa.String(length=16), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_leads_customer_email", "leads", ["customer_email"])
    op.create_index("ix_leads_phone", "leads", ["phone"])

    # 5. sales
    op.create_table(
        "sales",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("lead_id", sa.String(length=64), nullable=False),
        sa.Column("retailer_id", sa.String(length=64), nullable=False),
        sa.Column("campaign_id", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("sale_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="PENDING_QA", nullable=False),
        sa.Column("product_details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["retailer_id"], ["retailers.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sales_lead_id", "sales", ["lead_id"])
    op.create_index("ix_sales_retailer_id", "sales", ["retailer_id"])
    op.create_index("ix_sales_campaign_id", "sales", ["campaign_id"])
    op.create_index("ix_sales_agent_id", "sales", ["agent_id"])
    op.create_index("ix_sales_sale_date", "sales", ["sale_date"])
    op.create_index("ix_sales_status", "sales", ["status"])
    op.create_index("ix_sales_retailer_date", "sales", ["retailer_id", "sale_date"])

    # 6. recordings
    op.create_table(
        "recordings",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("sale_id", sa.String(length=64), nullable=False),
        sa.Column("artifact_id", sa.String(length=64), nullable=False),
        sa.Column("dialler_call_id", sa.String(length=64), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("call_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"]),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dialler_call_id"),
        sa.CheckConstraint("duration_seconds >= 0", name="ck_recording_duration_positive"),
    )
    op.create_index("ix_recordings_sale_id", "recordings", ["sale_id"])
    op.create_index("ix_recordings_artifact_id", "recordings", ["artifact_id"])
    op.create_index("ix_recordings_dialler_call_id", "recordings", ["dialler_call_id"])
    op.create_index("ix_recordings_call_date", "recordings", ["call_date"])

    # 7. transcripts
    op.create_table(
        "transcripts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("recording_id", sa.String(length=64), nullable=False),
        sa.Column("source_artifact_id", sa.String(length=64), nullable=False),
        sa.Column("output_artifact_id", sa.String(length=64), nullable=False),
        sa.Column("asr_provider", sa.String(length=64), nullable=False),
        sa.Column("asr_model", sa.String(length=64), nullable=False),
        sa.Column("asr_model_version", sa.String(length=64), nullable=False),
        sa.Column("diarization_provider", sa.String(length=64), nullable=False),
        sa.Column("diarization_version", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=16), server_default="en-AU", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["recording_id"], ["recordings.id"]),
        sa.ForeignKeyConstraint(["source_artifact_id"], ["artifacts.id"]),
        sa.ForeignKeyConstraint(["output_artifact_id"], ["artifacts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transcripts_recording_id", "transcripts", ["recording_id"])
    op.create_index("ix_transcripts_source_artifact_id", "transcripts", ["source_artifact_id"])
    op.create_index("ix_transcripts_output_artifact_id", "transcripts", ["output_artifact_id"])

    # 8. transcript_segments
    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("transcript_id", sa.String(length=64), nullable=False),
        sa.Column("segment_order", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.String(length=32), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("words_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("start_ms >= 0 AND end_ms >= start_ms", name="ck_segment_timestamps"),
    )
    op.create_index(
        "ix_transcript_segments_transcript_id", "transcript_segments", ["transcript_id"]
    )
    op.create_index("ix_transcript_segments_start_ms", "transcript_segments", ["start_ms"])
    op.create_index(
        "ix_segments_transcript_order", "transcript_segments", ["transcript_id", "segment_order"]
    )

    # 9. check_definitions
    op.create_table(
        "check_definitions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("check_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("check_type", sa.String(length=32), nullable=False),
        sa.Column("is_critical", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("default_weight", sa.Integer(), server_default="10", nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("check_code"),
    )
    op.create_index("ix_check_definitions_check_code", "check_definitions", ["check_code"])

    # 10. check_versions
    op.create_table(
        "check_versions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("check_id", sa.String(length=64), nullable=False),
        sa.Column("retailer_id", sa.String(length=64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parameters_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["check_id"], ["check_definitions.id"]),
        sa.ForeignKeyConstraint(["retailer_id"], ["retailers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "check_id", "retailer_id", "version_number", name="uq_check_retailer_version_number"
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_check_version_effective_dates",
        ),
        sa.CheckConstraint("version_number > 0", name="ck_check_version_number_positive"),
    )
    op.create_index("ix_check_versions_check_id", "check_versions", ["check_id"])
    op.create_index("ix_check_versions_retailer_id", "check_versions", ["retailer_id"])
    op.create_index("ix_check_versions_effective_from", "check_versions", ["effective_from"])
    op.create_index("ix_check_versions_effective_to", "check_versions", ["effective_to"])
    op.create_index(
        "ix_check_versions_lookup",
        "check_versions",
        ["retailer_id", "check_id", "effective_from", "effective_to"],
    )

    # 11. evaluation_runs
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("sale_id", sa.String(length=64), nullable=False),
        sa.Column("transcript_id", sa.String(length=64), nullable=False),
        sa.Column("checklist_version_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="COMPLETED", nullable=False),
        sa.Column("model_provider", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("prompt_template_version", sa.String(length=64), nullable=False),
        sa.Column("pipeline_git_sha", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("temperature", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"]),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evaluation_runs_sale_id", "evaluation_runs", ["sale_id"])
    op.create_index("ix_evaluation_runs_transcript_id", "evaluation_runs", ["transcript_id"])
    op.create_index(
        "ix_evaluation_runs_sale_transcript", "evaluation_runs", ["sale_id", "transcript_id"]
    )
    op.create_index(
        "ix_evaluation_runs_lineage",
        "evaluation_runs",
        ["sale_id", "transcript_id", "checklist_version_id", "policy_version"],
    )

    # 12. evaluation_results
    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("evaluation_run_id", sa.String(length=64), nullable=False),
        sa.Column("check_version_id", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("score_numeric", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["check_version_id"], ["check_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evaluation_run_id", "check_version_id", name="uq_run_check_version"),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0", name="ck_eval_result_confidence"
        ),
    )
    op.create_index(
        "ix_evaluation_results_evaluation_run_id", "evaluation_results", ["evaluation_run_id"]
    )
    op.create_index(
        "ix_evaluation_results_check_version_id", "evaluation_results", ["check_version_id"]
    )

    # 13. evaluation_evidences
    op.create_table(
        "evaluation_evidences",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("evaluation_result_id", sa.String(length=64), nullable=False),
        sa.Column("transcript_segment_id", sa.String(length=64), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("expected_value", sa.JSON(), nullable=True),
        sa.Column("observed_value", sa.JSON(), nullable=True),
        sa.Column("transcript_excerpt", sa.Text(), nullable=False),
        sa.Column("ai_explanation", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluation_result_id"], ["evaluation_results.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["transcript_segment_id"], ["transcript_segments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("start_ms >= 0 AND end_ms >= start_ms", name="ck_evidence_timestamps"),
    )
    op.create_index(
        "ix_evaluation_evidences_result_id", "evaluation_evidences", ["evaluation_result_id"]
    )
    op.create_index(
        "ix_evaluation_evidences_segment_id", "evaluation_evidences", ["transcript_segment_id"]
    )

    # 14. gate_decisions
    op.create_table(
        "gate_decisions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("sale_id", sa.String(length=64), nullable=False),
        sa.Column("evaluation_run_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("decision_reason_code", sa.String(length=64), nullable=False),
        sa.Column("auto_submitted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"]),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["evaluation_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evaluation_run_id"),
    )
    op.create_index("ix_gate_decisions_sale_id", "gate_decisions", ["sale_id"])
    op.create_index("ix_gate_decisions_evaluation_run_id", "gate_decisions", ["evaluation_run_id"])

    # 15. human_reviews
    op.create_table(
        "human_reviews",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("gate_decision_id", sa.String(length=64), nullable=False),
        sa.Column("reviewer_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("reason_notes", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["gate_decision_id"], ["gate_decisions.id"]),
        sa.ForeignKeyConstraint(["reviewer_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_human_reviews_gate_decision_id", "human_reviews", ["gate_decision_id"])
    op.create_index("ix_human_reviews_reviewer_id", "human_reviews", ["reviewer_id"])

    # 16. audit_events
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_entity_type", "audit_events", ["entity_type"])
    op.create_index("ix_audit_events_entity_id", "audit_events", ["entity_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])
    op.create_index("ix_audit_events_correlation_id", "audit_events", ["correlation_id"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_index(
        "ix_audit_entity_lookup", "audit_events", ["entity_type", "entity_id", "created_at"]
    )
    op.create_index("ix_audit_actor_lookup", "audit_events", ["actor_id", "created_at"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("human_reviews")
    op.drop_table("gate_decisions")
    op.drop_table("evaluation_evidences")
    op.drop_table("evaluation_results")
    op.drop_table("evaluation_runs")
    op.drop_table("check_versions")
    op.drop_table("check_definitions")
    op.drop_table("transcript_segments")
    op.drop_table("transcripts")
    op.drop_table("recordings")
    op.drop_table("sales")
    op.drop_table("leads")
    op.drop_table("agents")
    op.drop_table("campaigns")
    op.drop_table("retailers")
