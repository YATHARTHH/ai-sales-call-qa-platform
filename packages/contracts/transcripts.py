"""Pydantic v2 schemas for transcripts, paginated segments, and speech behavior."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WordTimingSchema(BaseModel):
    """Word-level alignment and acoustic confidence."""

    model_config = ConfigDict(from_attributes=True)

    word: str
    start_ms: int = Field(..., ge=0)
    end_ms: int = Field(..., ge=0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class InterruptionCandidateSchema(BaseModel):
    """Candidate conversational interruption where a speaker overlaps another speaker."""

    model_config = ConfigDict(from_attributes=True)

    speaker_label: str
    interrupted_speaker_label: str
    start_ms: int = Field(..., ge=0)
    overlap_duration_ms: int = Field(..., ge=0)


class SilenceIntervalSchema(BaseModel):
    """Dead air silence interval between speech turns."""

    model_config = ConfigDict(from_attributes=True)

    start_ms: int = Field(..., ge=0)
    end_ms: int = Field(..., ge=0)
    duration_ms: int = Field(..., ge=0)


class TranscriptSegmentResponse(BaseModel):
    """Timestamped utterance segment with speaker attribution."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    segment_order: int
    speaker_label: str
    business_role: str
    role_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    start_ms: int = Field(..., ge=0)
    end_ms: int = Field(..., ge=0)
    text: str
    words: list[WordTimingSchema] | None = None


class PaginatedSegmentsResponse(BaseModel):
    """Paginated collection of utterance segments."""

    model_config = ConfigDict(from_attributes=True)

    items: list[TranscriptSegmentResponse]
    total: int = Field(..., ge=0)
    offset: int = Field(..., ge=0)
    limit: int = Field(..., ge=1, le=500)


class SpeechBehaviorResponse(BaseModel):
    """Objective speech behavior analysis metrics."""

    model_config = ConfigDict(from_attributes=True)

    audio_duration_ms: int
    transcribed_coverage_end_ms: int
    leading_uncovered_ms: int
    trailing_uncovered_ms: int
    has_uncovered_audio: bool
    agent_talk_ms: int
    customer_talk_ms: int
    total_speech_ms: int
    agent_talk_percentage: float
    customer_talk_percentage: float
    conversational_occupancy_percentage: float
    agent_words_per_minute: float
    customer_words_per_minute: float
    dead_air_gaps: list[SilenceIntervalSchema]
    interruption_candidates: list[InterruptionCandidateSchema]


class TranscriptResponse(BaseModel):
    """Transcript metadata, availability status, and provenance identity."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    recording_id: str
    source_artifact_id: str
    output_artifact_id: str
    transcription_key: str
    transcription_identity: str
    availability: str
    processor_version: str
    asr_provider: str
    asr_model: str
    asr_model_version: str
    diarization_provider: str
    diarization_version: str
    language: str
    created_at: datetime
