"""Unit tests for untrusted provider output validation and completeness states."""

import pytest

from packages.application.ports.transcription import (
    RawUtterance,
    TranscriptionResult,
    WordTiming,
)
from packages.application.services.provider_validator import ProviderOutputValidator
from packages.domain.exceptions import ProviderOutputValidationError
from packages.domain.transcript import TranscriptAvailability


def build_result(utterances):
    return TranscriptionResult(
        utterances=utterances,
        language="en-AU",
        asr_provider="test",
        asr_model="test-m",
        asr_model_version="1",
        diarization_provider="test",
        diarization_version="1",
        transcription_config_hash="h1",
        diarization_config_hash="h2",
    )


def test_validator_accepts_valid_utterances():
    validator = ProviderOutputValidator()
    result = build_result([
        RawUtterance(
            speaker_label="SPEAKER_00",
            start_ms=1000,
            end_ms=4000,
            text="Hello world.",
            words=[
                WordTiming("Hello", 1000, 2000, 0.95),
                WordTiming("world.", 2100, 3900, 0.98),
            ],
        )
    ])
    status = validator.validate(result, audio_duration_ms=5000)
    assert status == TranscriptAvailability.AVAILABLE


def test_validator_rejects_negative_timestamps():
    validator = ProviderOutputValidator()
    result = build_result([
        RawUtterance(
            speaker_label="SPEAKER_00",
            start_ms=-100,
            end_ms=2000,
            text="Invalid negative start.",
        )
    ])
    with pytest.raises(ProviderOutputValidationError) as exc:
        validator.validate(result, audio_duration_ms=5000)
    assert "negative start_ms" in exc.value.message


def test_validator_rejects_inverted_timestamps():
    validator = ProviderOutputValidator()
    result = build_result([
        RawUtterance(
            speaker_label="SPEAKER_00",
            start_ms=3000,
            end_ms=2000,
            text="Inverted time.",
        )
    ])
    with pytest.raises(ProviderOutputValidationError) as exc:
        validator.validate(result, audio_duration_ms=5000)
    assert "invalid interval" in exc.value.message


def test_validator_rejects_negative_word_durations():
    validator = ProviderOutputValidator()
    result = build_result([
        RawUtterance(
            speaker_label="SPEAKER_00",
            start_ms=1000,
            end_ms=4000,
            text="Word test.",
            words=[
                WordTiming("Word", 3000, 2000, 0.9),  # end < start
            ],
        )
    ])
    with pytest.raises(ProviderOutputValidationError) as exc:
        validator.validate(result, audio_duration_ms=5000)
    assert "negative duration" in exc.value.message


def test_validator_detects_partial_transcript_on_low_coverage():
    """When utterances cover less than the configured threshold (e.g. 50%), emits PARTIAL."""
    validator = ProviderOutputValidator(coverage_partial_threshold=0.5)

    # 10 minute call (600,000 ms), but utterances stop after only 1 minute (60,000 ms) = 10% coverage
    result = build_result([
        RawUtterance(
            speaker_label="SPEAKER_00",
            start_ms=1000,
            end_ms=60000,
            text="Truncated call content.",
        )
    ])
    status = validator.validate(result, audio_duration_ms=600000)
    assert status == TranscriptAvailability.PARTIAL
