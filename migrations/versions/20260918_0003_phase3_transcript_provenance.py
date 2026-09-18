"""Phase 3 transcript provenance, completeness, lease fencing, and speech metrics.

Revision ID: 20260918_0003
Revises: 20260918_0002
Create Date: 2026-09-18 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260918_0003"
down_revision: str | None = "20260918_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Add lease_generation to pipeline_jobs
    op.add_column(
        "pipeline_jobs",
        sa.Column("lease_generation", sa.Integer(), server_default="0", nullable=False),
    )

    # 2. Check for unexpected legacy records in transcripts table
    transcript_count = conn.execute(sa.text("SELECT COUNT(*) FROM transcripts")).scalar()
    if transcript_count and transcript_count > 0:
        # If records exist, verify they have valid provenance or fail fast
        raise RuntimeError(
            f"Found {transcript_count} legacy transcript rows without truthful provenance. "
            "Automated migration cannot invent synthetic transcription keys. Manual review required."
        )

    # 3. Add Phase 3 columns to transcripts
    op.add_column("transcripts", sa.Column("transcription_key", sa.String(128), nullable=True))
    op.add_column("transcripts", sa.Column("transcription_identity", sa.String(255), nullable=True))
    op.add_column(
        "transcripts",
        sa.Column("availability", sa.String(32), server_default="AVAILABLE", nullable=False),
    )
    op.add_column("transcripts", sa.Column("processor_version", sa.String(64), nullable=True))
    op.add_column("transcripts", sa.Column("transcription_config_hash", sa.String(64), nullable=True))
    op.add_column("transcripts", sa.Column("diarization_config_hash", sa.String(64), nullable=True))
    op.add_column("transcripts", sa.Column("role_mapping_version", sa.String(64), nullable=True))
    op.add_column(
        "transcripts",
        sa.Column("audio_duration_ms", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "transcripts",
        sa.Column("transcribed_coverage_end_ms", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "transcripts",
        sa.Column("leading_uncovered_ms", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "transcripts",
        sa.Column("trailing_uncovered_ms", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("transcripts", sa.Column("behavior_json", sa.JSON(), nullable=True))

    # Create unique index on transcription_key
    op.create_index(
        "ix_transcripts_transcription_key",
        "transcripts",
        ["transcription_key"],
        unique=True,
    )

    # Enforce NOT NULL on provenance columns
    with op.batch_alter_table("transcripts") as batch_op:
        batch_op.alter_column("transcription_key", nullable=False)
        batch_op.alter_column("transcription_identity", nullable=False)
        batch_op.alter_column("processor_version", nullable=False)
        batch_op.alter_column("transcription_config_hash", nullable=False)
        batch_op.alter_column("diarization_config_hash", nullable=False)
        batch_op.alter_column("role_mapping_version", nullable=False)

    # 4. Update transcript_segments table
    op.add_column(
        "transcript_segments",
        sa.Column("speaker_label", sa.String(32), server_default="SPEAKER_00", nullable=False),
    )
    op.add_column(
        "transcript_segments",
        sa.Column("business_role", sa.String(32), server_default="UNKNOWN", nullable=False),
    )
    op.add_column(
        "transcript_segments",
        sa.Column("role_confidence", sa.Float(), server_default="1.0", nullable=False),
    )

    # Migrate legacy speaker column to business_role if records exist
    conn.execute(
        sa.text("UPDATE transcript_segments SET business_role = speaker WHERE speaker IS NOT NULL")
    )

    with op.batch_alter_table("transcript_segments") as batch_op:
        batch_op.drop_column("speaker")

    # Add composite index on transcript_id and start_ms
    op.create_index(
        "ix_segments_transcript_time",
        "transcript_segments",
        ["transcript_id", "start_ms"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_segments_transcript_time", table_name="transcript_segments")
    with op.batch_alter_table("transcript_segments") as batch_op:
        batch_op.add_column(sa.Column("speaker", sa.String(32), nullable=True))
        batch_op.drop_column("role_confidence")
        batch_op.drop_column("business_role")
        batch_op.drop_column("speaker_label")

    op.drop_index("ix_transcripts_transcription_key", table_name="transcripts")
    with op.batch_alter_table("transcripts") as batch_op:
        batch_op.drop_column("behavior_json")
        batch_op.drop_column("trailing_uncovered_ms")
        batch_op.drop_column("leading_uncovered_ms")
        batch_op.drop_column("transcribed_coverage_end_ms")
        batch_op.drop_column("audio_duration_ms")
        batch_op.drop_column("role_mapping_version")
        batch_op.drop_column("diarization_config_hash")
        batch_op.drop_column("transcription_config_hash")
        batch_op.drop_column("processor_version")
        batch_op.drop_column("availability")
        batch_op.drop_column("transcription_identity")
        batch_op.drop_column("transcription_key")

    op.drop_column("pipeline_jobs", "lease_generation")
