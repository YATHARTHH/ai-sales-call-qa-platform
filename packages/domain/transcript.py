"""Domain models for recordings, transcripts, and speaker segments."""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class SpeakerType(StrEnum):
    AGENT = "AGENT"
    CUSTOMER = "CUSTOMER"
    UNKNOWN = "UNKNOWN"


class TranscriptAvailability(StrEnum):
    NOT_AVAILABLE = "NOT_AVAILABLE"
    PARTIAL = "PARTIAL"
    AVAILABLE = "AVAILABLE"
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True)
class Recording:
    """Represents a call audio recording linked to an immutable audio artifact."""

    id: str
    sale_id: str
    artifact_id: str  # Foreign reference to immutable audio Artifact
    dialler_call_id: str
    duration_seconds: float
    call_date: datetime
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def validated_audio_duration_ms(self) -> int:
        """Authoritative duration in milliseconds derived from container inspection."""
        return int(self.duration_seconds * 1000)

    @classmethod
    def create(
        cls,
        sale_id: str,
        artifact_id: str,
        dialler_call_id: str,
        duration_seconds: float,
        call_date: datetime,
        recording_id: str | None = None,
    ) -> "Recording":
        return cls(
            id=recording_id or str(uuid.uuid4()),
            sale_id=sale_id,
            artifact_id=artifact_id,
            dialler_call_id=dialler_call_id,
            duration_seconds=duration_seconds,
            call_date=call_date,
            created_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class Transcript:
    """Represents a speech-to-text transcript linked to immutable source and output artifacts."""

    id: str
    recording_id: str
    source_artifact_id: str  # Audio artifact ID
    output_artifact_id: str  # Transcript JSON artifact ID in storage
    asr_provider: str
    asr_model: str
    asr_model_version: str
    diarization_provider: str
    diarization_version: str
    language: str = "en-AU"
    transcription_key: str = ""
    transcription_identity: str = ""
    availability: TranscriptAvailability = TranscriptAvailability.AVAILABLE
    processor_version: str = ""
    transcription_config_hash: str = ""
    diarization_config_hash: str = ""
    role_mapping_version: str = ""
    audio_duration_ms: int = 0
    transcribed_coverage_end_ms: int = 0
    leading_uncovered_ms: int = 0
    trailing_uncovered_ms: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def build_processor_version(
        cls, asr_model: str, asr_version: str, diarize_model: str, diarize_version: str
    ) -> str:
        return f"{asr_model}@{asr_version}+{diarize_model}@{diarize_version}"

    @classmethod
    def compute_transcription_key(
        cls,
        source_audio_hash: str,
        processor_version: str,
        transcription_config_hash: str,
        diarization_config_hash: str,
        role_mapping_version: str,
    ) -> str:
        canonical = ":".join([
            "transcription",
            source_audio_hash,
            processor_version,
            transcription_config_hash,
            diarization_config_hash,
            role_mapping_version,
        ])
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def build_transcription_identity(cls, source_audio_hash: str, processor_version: str) -> str:
        return f"transcription:{source_audio_hash[:8]}:{processor_version}"

    @classmethod
    def build_idempotency_key(
        cls, recording_id: str, source_artifact_hash: str, processor_version: str
    ) -> str:
        return f"{recording_id}:transcription:{source_artifact_hash}:{processor_version}"


@dataclass(frozen=True)
class TranscriptSegment:
    """Timestamped utterance segment with speaker attribution."""

    id: str
    transcript_id: str
    segment_order: int
    speaker_label: str
    business_role: SpeakerType
    start_ms: int
    end_ms: int
    text: str
    role_confidence: float = 1.0
    words_json: list[dict[str, Any]] = field(default_factory=list)

    @property
    def speaker(self) -> SpeakerType:
        """Deprecated alias: use business_role instead."""
        return self.business_role

    @classmethod
    def create(
        cls,
        transcript_id: str,
        segment_order: int,
        speaker: SpeakerType | None = None,
        start_ms: int = 0,
        end_ms: int = 0,
        text: str = "",
        speaker_label: str | None = None,
        business_role: SpeakerType | None = None,
        role_confidence: float = 1.0,
        words_json: list[dict[str, Any]] | None = None,
        segment_id: str | None = None,
    ) -> "TranscriptSegment":
        role = business_role or speaker or SpeakerType.UNKNOWN
        label = (
            speaker_label
            or ("SPEAKER_00" if role == SpeakerType.AGENT else "SPEAKER_01" if role == SpeakerType.CUSTOMER else "SPEAKER_UNKNOWN")
        )
        return cls(
            id=segment_id or str(uuid.uuid4()),
            transcript_id=transcript_id,
            segment_order=segment_order,
            speaker_label=label,
            business_role=role,
            role_confidence=role_confidence,
            start_ms=start_ms,
            end_ms=end_ms,
            text=text.strip(),
            words_json=words_json or [],
        )
