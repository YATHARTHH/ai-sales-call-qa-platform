"""Initial database schema: artifacts and pipeline_jobs tables.

Revision ID: 20260918_0001
Revises:
Create Date: 2026-09-18 18:50:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260918_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create artifacts table
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("lead_id", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_hash"),
    )
    op.create_index("ix_artifacts_lead_id", "artifacts", ["lead_id"])
    op.create_index("ix_artifacts_content_hash", "artifacts", ["content_hash"])
    op.create_index("ix_artifacts_lead_created", "artifacts", ["lead_id", "created_at"])

    # 2. Create pipeline_jobs table
    op.create_table(
        "pipeline_jobs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("recording_id", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("failure_category", sa.String(length=64), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_jobs_recording_id", "pipeline_jobs", ["recording_id"])
    op.create_index("ix_jobs_stage", "pipeline_jobs", ["stage"])
    op.create_index("ix_jobs_status", "pipeline_jobs", ["status"])
    op.create_index("ix_jobs_idempotency_key", "pipeline_jobs", ["idempotency_key"])
    op.create_index("ix_jobs_worker_id", "pipeline_jobs", ["worker_id"])
    op.create_index("ix_jobs_lease_until", "pipeline_jobs", ["lease_until"])
    op.create_index("ix_jobs_status_lease", "pipeline_jobs", ["status", "lease_until"])


def downgrade() -> None:
    op.drop_table("pipeline_jobs")
    op.drop_table("artifacts")
