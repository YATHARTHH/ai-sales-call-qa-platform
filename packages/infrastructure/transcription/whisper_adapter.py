"""Faster-Whisper optional adapter for local speech-to-text inference."""

import hashlib
import os

from packages.application.ports.transcription import (
    AudioSource,
    RawUtterance,
    TranscriptionPort,
    TranscriptionResult,
    WordTiming,
)
from packages.domain.exceptions import ArtifactIntegrityError, DomainError
from packages.observability.logging import get_logger

logger = get_logger("transcription.whisper")


class ProviderConfigurationError(DomainError):
    """Raised when an optional ASR provider library is not installed or misconfigured."""

    def __init__(self, message: str):
        super().__init__(message, code="PROVIDER_CONFIGURATION_ERROR")


class FasterWhisperAdapter(TranscriptionPort):
    """Local ASR adapter utilizing faster-whisper (CTranslate2) when optional dependencies are installed."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.transcription_config_hash = hashlib.sha256(
            f"whisper-{model_size}-{device}-{compute_type}".encode()
        ).hexdigest()[:16]
        self.diarization_config_hash = hashlib.sha256(b"pyannote-community-v3").hexdigest()[:16]

    def provider_name(self) -> str:
        return f"faster-whisper-{self.model_size}"

    async def transcribe(self, source: AudioSource) -> TranscriptionResult:
        if not source.local_path or not os.path.exists(source.local_path):
            raise ArtifactIntegrityError(f"AudioSource file missing: '{source.local_path}'")

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ProviderConfigurationError(
                "The 'faster-whisper' package is not installed. Install with 'pip install .[speech]' "
                "or use DeterministicTranscriptionAdapter for local testing."
            ) from exc

        logger.info(
            "running_faster_whisper_transcription",
            model=self.model_size,
            device=self.device,
            path=source.local_path,
        )

        model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
        segments_gen, info = model.transcribe(
            source.local_path, word_timestamps=True, language="en"
        )

        utterances: list[RawUtterance] = []
        for s in segments_gen:
            words = [
                WordTiming(
                    word=w.word,
                    start_ms=int(w.start * 1000),
                    end_ms=int(w.end * 1000),
                    confidence=w.probability,
                )
                for w in (s.words or [])
            ]
            utterances.append(
                RawUtterance(
                    speaker_label="SPEAKER_00",  # default single-speaker fallback
                    start_ms=int(s.start * 1000),
                    end_ms=int(s.end * 1000),
                    text=s.text.strip(),
                    words=words,
                )
            )

        return TranscriptionResult(
            utterances=utterances,
            language=info.language or "en-AU",
            asr_provider="faster-whisper",
            asr_model=f"whisper-{self.model_size}",
            asr_model_version="faster-whisper-v1",
            diarization_provider="builtin-energy",
            diarization_version="v1",
            transcription_config_hash=self.transcription_config_hash,
            diarization_config_hash=self.diarization_config_hash,
            processing_mode="live_asr",
        )
