"""SQLAlchemy models for recordings, transcripts, and speaker segments."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from packages.infrastructure.database.base import Base


class RecordingModel(Base):
    __tablename__ = "recordings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sale_id: Mapped[str] = mapped_column(String(64), ForeignKey("sales.id"), nullable=False, index=True)
    artifact_id: Mapped[str] = mapped_column(String(64), ForeignKey("artifacts.id"), nullable=False, index=True)
    dialler_call_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    call_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    __table_args__ = (
        CheckConstraint("duration_seconds >= 0", name="ck_recording_duration_positive"),
    )


class TranscriptModel(Base):
    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    recording_id: Mapped[str] = mapped_column(String(64), ForeignKey("recordings.id"), nullable=False, index=True)
    source_artifact_id: Mapped[str] = mapped_column(String(64), ForeignKey("artifacts.id"), nullable=False, index=True)
    output_artifact_id: Mapped[str] = mapped_column(String(64), ForeignKey("artifacts.id"), nullable=False, index=True)
    asr_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    asr_model: Mapped[str] = mapped_column(String(64), nullable=False)
    asr_model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    diarization_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    diarization_version: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="en-AU", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    recording: Mapped[RecordingModel] = relationship()
    segments: Mapped[list["TranscriptSegmentModel"]] = relationship(
        back_populates="transcript", cascade="all, delete-orphan", order_by="TranscriptSegmentModel.segment_order"
    )


class TranscriptSegmentModel(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    transcript_id: Mapped[str] = mapped_column(String(64), ForeignKey("transcripts.id"), nullable=False, index=True)
    segment_order: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(String(32), nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    words_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    transcript: Mapped[TranscriptModel] = relationship(back_populates="segments")

    __table_args__ = (
        Index("ix_segments_transcript_order", "transcript_id", "segment_order"),
        CheckConstraint("start_ms >= 0 AND end_ms >= start_ms", name="ck_segment_timestamps"),
    )
