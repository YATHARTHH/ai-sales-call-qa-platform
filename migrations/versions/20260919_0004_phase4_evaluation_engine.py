"""Phase 4 Multi-Tier QA Evaluation & Deterministic Policy Gate Engine.

Revision ID: 20260919_0004
Revises: 20260918_0003
Create Date: 2026-09-19 11:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260919_0004"
down_revision: str | None = "20260918_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Update check_versions table
    with op.batch_alter_table("check_versions") as batch_op:
        batch_op.add_column(
            sa.Column("jurisdiction", sa.String(32), server_default="AU-VIC", nullable=False)
        )
        batch_op.add_column(
            sa.Column("regulatory_reference", sa.String(128), nullable=True)
        )
        batch_op.add_column(
            sa.Column("rule_type", sa.String(32), server_default="LEGAL_REQUIREMENT", nullable=False)
        )
        batch_op.add_column(
            sa.Column("applicability_json", sa.JSON(), nullable=True)
        )

    # 2. Update evaluation_runs table
    with op.batch_alter_table("evaluation_runs") as batch_op:
        batch_op.add_column(
            sa.Column("tenant_id", sa.String(64), server_default="default-tenant", nullable=False)
        )
        batch_op.add_column(
            sa.Column("input_snapshot_id", sa.String(64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("input_snapshot_hash", sa.String(64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("input_snapshot_json", sa.JSON(), nullable=True)
        )
        batch_op.create_index(
            "ix_evaluation_runs_tenant", ["tenant_id", "created_at"]
        )

    # 3. Update evaluation_results table
    with op.batch_alter_table("evaluation_results") as batch_op:
        batch_op.add_column(
            sa.Column("check_id", sa.String(64), server_default="", nullable=False)
        )
        batch_op.add_column(
            sa.Column("is_critical", sa.Boolean(), server_default=sa.true(), nullable=False)
        )
        batch_op.add_column(
            sa.Column("reason_codes", sa.JSON(), server_default="[]", nullable=False)
        )
        batch_op.alter_column("confidence", nullable=True)
        batch_op.alter_column("score_numeric", nullable=True)

    # 4. Update evaluation_evidences table
    with op.batch_alter_table("evaluation_evidences") as batch_op:
        batch_op.add_column(
            sa.Column("transcript_id", sa.String(64), server_default="", nullable=False)
        )
        batch_op.add_column(
            sa.Column("speaker", sa.String(32), server_default="AGENT", nullable=False)
        )
        batch_op.add_column(
            sa.Column("evidence_type", sa.String(32), server_default="SUPPORTING", nullable=False)
        )
        batch_op.add_column(
            sa.Column("comparison_source", sa.String(64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("expected_value_source", sa.String(64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("observed_value_source", sa.String(64), nullable=True)
        )

    # 5. Update gate_decisions table
    with op.batch_alter_table("gate_decisions") as batch_op:
        batch_op.add_column(
            sa.Column("reason_codes", sa.JSON(), server_default="[]", nullable=False)
        )
        batch_op.add_column(
            sa.Column("blocking_check_ids", sa.JSON(), server_default="[]", nullable=False)
        )
        batch_op.add_column(
            sa.Column("warnings", sa.JSON(), server_default="[]", nullable=False)
        )

    # 6. Update human_reviews table
    with op.batch_alter_table("human_reviews") as batch_op:
        batch_op.add_column(
            sa.Column("reviewer_role", sa.String(32), server_default="qa_auditor", nullable=False)
        )

    # 7. Create outbox_events table
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("event_schema_version", sa.String(16), server_default="v1", nullable=False),
        sa.Column("idempotency_key", sa.String(128), unique=True, nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_outbox_unpublished",
        "outbox_events",
        ["published_at", "locked_until", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_unpublished", table_name="outbox_events")
    op.drop_table("outbox_events")

    with op.batch_alter_table("human_reviews") as batch_op:
        batch_op.drop_column("reviewer_role")

    with op.batch_alter_table("gate_decisions") as batch_op:
        batch_op.drop_column("warnings")
        batch_op.drop_column("blocking_check_ids")
        batch_op.drop_column("reason_codes")

    with op.batch_alter_table("evaluation_evidences") as batch_op:
        batch_op.drop_column("observed_value_source")
        batch_op.drop_column("expected_value_source")
        batch_op.drop_column("comparison_source")
        batch_op.drop_column("evidence_type")
        batch_op.drop_column("speaker")
        batch_op.drop_column("transcript_id")

    with op.batch_alter_table("evaluation_results") as batch_op:
        batch_op.alter_column("score_numeric", nullable=False)
        batch_op.alter_column("confidence", nullable=False)
        batch_op.drop_column("reason_codes")
        batch_op.drop_column("is_critical")
        batch_op.drop_column("check_id")

    op.drop_index("ix_evaluation_runs_tenant", table_name="evaluation_runs")
    with op.batch_alter_table("evaluation_runs") as batch_op:
        batch_op.drop_column("input_snapshot_json")
        batch_op.drop_column("input_snapshot_hash")
        batch_op.drop_column("input_snapshot_id")
        batch_op.drop_column("tenant_id")

    with op.batch_alter_table("check_versions") as batch_op:
        batch_op.drop_column("applicability_json")
        batch_op.drop_column("rule_type")
        batch_op.drop_column("regulatory_reference")
        batch_op.drop_column("jurisdiction")
