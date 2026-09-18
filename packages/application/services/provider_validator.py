"""Validation service for untrusted ASR and diarization provider output."""

from packages.application.ports.transcription import TranscriptionResult
from packages.domain.exceptions import ProviderOutputValidationError
from packages.domain.transcript import TranscriptAvailability
from packages.observability.logging import get_logger

logger = get_logger("service.provider_validator")


class ProviderOutputValidator:
    """Validates raw utterances from transcription providers against duration and sanity bounds."""

    def __init__(
        self,
        duration_tolerance_ms: int = 1000,
        max_utterance_length_chars: int = 10_000,
        coverage_partial_threshold: float = 0.5,
    ):
        self.duration_tolerance_ms = duration_tolerance_ms
        self.max_utterance_length_chars = max_utterance_length_chars
        self.coverage_partial_threshold = coverage_partial_threshold

    def validate(
        self, result: TranscriptionResult, audio_duration_ms: int
    ) -> TranscriptAvailability:
        """Validate provider output.

        Raises ProviderOutputValidationError on malformed data.
        Returns TranscriptAvailability (AVAILABLE or PARTIAL).
        """
        if not result.utterances:
            if audio_duration_ms > 5000:
                logger.warning(
                    "provider_empty_utterances_for_audio",
                    audio_duration_ms=audio_duration_ms,
                )
                return TranscriptAvailability.PARTIAL
            return TranscriptAvailability.AVAILABLE

        max_allowed_end = audio_duration_ms + self.duration_tolerance_ms
        is_partial = False

        for i, u in enumerate(result.utterances):
            # 1. Monotonic utterance timings
            if u.start_ms < 0:
                raise ProviderOutputValidationError(
                    f"Utterance {i} has negative start_ms: {u.start_ms}"
                )
            if u.end_ms <= u.start_ms:
                raise ProviderOutputValidationError(
                    f"Utterance {i} has invalid interval: start_ms={u.start_ms}, end_ms={u.end_ms}"
                )
            if u.end_ms > max_allowed_end:
                raise ProviderOutputValidationError(
                    f"Utterance {i} ends at {u.end_ms} ms, exceeding audio duration {audio_duration_ms} ms (+ {self.duration_tolerance_ms} ms tolerance)"
                )

            # 2. Speaker label
            if not u.speaker_label or not u.speaker_label.strip():
                raise ProviderOutputValidationError(f"Utterance {i} has empty speaker label.")

            # 3. Text bounds
            if len(u.text) > self.max_utterance_length_chars:
                raise ProviderOutputValidationError(
                    f"Utterance {i} text length ({len(u.text)}) exceeds limit of {self.max_utterance_length_chars}"
                )

            # 4. Word timings validation
            for w in u.words:
                if w.start_ms < u.start_ms - 50:
                    raise ProviderOutputValidationError(
                        f"Word '{w.word}' starts at {w.start_ms} ms before utterance start {u.start_ms} ms"
                    )
                if w.end_ms > u.end_ms + 50:
                    raise ProviderOutputValidationError(
                        f"Word '{w.word}' ends at {w.end_ms} ms after utterance end {u.end_ms} ms"
                    )
                if w.end_ms < w.start_ms:
                    raise ProviderOutputValidationError(
                        f"Word '{w.word}' has negative duration: {w.start_ms} to {w.end_ms} ms"
                    )
                if w.confidence is not None and not (0.0 <= w.confidence <= 1.0):
                    raise ProviderOutputValidationError(
                        f"Word '{w.word}' has out-of-range confidence: {w.confidence}"
                    )

        # Check coverage completeness
        last_end = max(u.end_ms for u in result.utterances)
        if audio_duration_ms > 0:
            coverage = last_end / audio_duration_ms
            if coverage < self.coverage_partial_threshold:
                logger.warning("transcript_coverage_low", coverage=coverage)
                is_partial = True

        return TranscriptAvailability.PARTIAL if is_partial else TranscriptAvailability.AVAILABLE
