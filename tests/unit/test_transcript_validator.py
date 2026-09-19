"""Unit tests for pre-evaluation transcript quality and lineage validator."""

from datetime import UTC, datetime

from packages.application.services.transcript_validator import (
    TranscriptIntegrityValidator,
)
from packages.domain.transcript import (
    Recording,
    SpeakerType,
    Transcript,
    TranscriptAvailability,
    TranscriptSegment,
)


def create_mock_recording(duration_seconds: float = 60.0, artifact_id: str = "art-123"):
    return Recording.create(
        sale_id="sale-1",
        artifact_id=artifact_id,
        dialler_call_id="call-1",
        duration_seconds=duration_seconds,
        call_date=datetime.now(UTC),
    )


def create_mock_transcript(source_artifact_id: str = "art-123"):
    return Transcript(
        id="tx-1",
        recording_id="rec-1",
        source_artifact_id=source_artifact_id,
        output_artifact_id="art-tx-1",
        asr_provider="whisper",
        asr_model="large-v3",
        asr_model_version="1.0",
        diarization_provider="pyannote",
        diarization_version="3.1",
        availability=TranscriptAvailability.AVAILABLE,
        audio_duration_ms=60000,
    )


def test_transcript_validator_valid_conversation():
    rec = create_mock_recording(60.0)
    tx = create_mock_transcript()
    segments = [
        TranscriptSegment.create(
            transcript_id="tx-1",
            segment_order=1,
            business_role=SpeakerType.AGENT,
            start_ms=0,
            end_ms=5000,
            text="Hello thank you for calling Energy Australia.",
        ),
        TranscriptSegment.create(
            transcript_id="tx-1",
            segment_order=2,
            business_role=SpeakerType.CUSTOMER,
            start_ms=4500,  # 500ms normal conversational overlap
            end_ms=8000,
            text="Hi I want to compare electricity rates.",
        ),
    ]

    res = TranscriptIntegrityValidator.validate(tx, segments, rec)
    assert res.is_valid is True
    assert len(res.reason_codes) == 0
    assert res.agent_duration_ratio > 0
    assert res.customer_duration_ratio > 0
    assert res.has_active_conversation is True


def test_transcript_validator_rejects_disordered_segments():
    rec = create_mock_recording(60.0)
    tx = create_mock_transcript()
    segments = [
        TranscriptSegment.create(
            transcript_id="tx-1",
            segment_order=1,
            business_role=SpeakerType.AGENT,
            start_ms=0,
            end_ms=2000,
            text="First",
        ),
        TranscriptSegment.create(
            transcript_id="tx-1",
            segment_order=3,  # Gap in ordering (missing 2)
            business_role=SpeakerType.CUSTOMER,
            start_ms=2100,
            end_ms=4000,
            text="Third",
        ),
    ]

    res = TranscriptIntegrityValidator.validate(tx, segments, rec)
    assert res.is_valid is False
    assert any("INVALID_SEGMENT_ORDER" in code for code in res.reason_codes)


def test_transcript_validator_rejects_inverted_timestamps():
    rec = create_mock_recording(60.0)
    tx = create_mock_transcript()
    segments = [
        TranscriptSegment.create(
            transcript_id="tx-1",
            segment_order=1,
            business_role=SpeakerType.AGENT,
            start_ms=5000,
            end_ms=5000,  # Zero duration (end == start)
            text="Instantaneous",
        )
    ]

    res = TranscriptIntegrityValidator.validate(tx, segments, rec)
    assert res.is_valid is False
    assert any("INVERTED_TIMESTAMPS" in code for code in res.reason_codes)


def test_transcript_validator_rejects_timestamp_exceeding_duration():
    rec = create_mock_recording(10.0)  # 10s = 10000ms
    tx = create_mock_transcript()
    segments = [
        TranscriptSegment.create(
            transcript_id="tx-1",
            segment_order=1,
            business_role=SpeakerType.AGENT,
            start_ms=0,
            end_ms=12000,  # 12s exceeds 10s
            text="Too long",
        )
    ]

    res = TranscriptIntegrityValidator.validate(tx, segments, rec)
    assert res.is_valid is False
    assert any("TIMESTAMP_EXCEEDS_DURATION" in code for code in res.reason_codes)


def test_transcript_validator_rejects_lineage_mismatch():
    rec = create_mock_recording(60.0, artifact_id="art-expected")
    tx = create_mock_transcript(source_artifact_id="art-unexpected")
    segments = [
        TranscriptSegment.create(
            transcript_id="tx-1",
            segment_order=1,
            business_role=SpeakerType.AGENT,
            start_ms=0,
            end_ms=2000,
            text="Hi",
        )
    ]

    res = TranscriptIntegrityValidator.validate(tx, segments, rec)
    assert res.is_valid is False
    assert "LINEAGE_ARTIFACT_MISMATCH" in res.reason_codes
