"""Transcription port contract for Speech-to-Text / Diarization engines."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AudioSource:
    """Immutable, bounded audio source passed to transcription adapters."""

    local_path: str
    content_hash: str
    mime_type: str
    size_bytes: int


@dataclass(frozen=True)
class WordTiming:
    """Word-level alignment timestamp and optional acoustic confidence."""

    word: str
    start_ms: int
    end_ms: int
    confidence: float | None = None


@dataclass(frozen=True)
class RawUtterance:
    """Continuous speech utterance produced by ASR and diarization before role assignment."""

    speaker_label: str
    start_ms: int
    end_ms: int
    text: str
    words: list[WordTiming] = field(default_factory=list)


@dataclass(frozen=True)
class TranscriptionResult:
    """Canonical raw output of speech transcription and speaker diarization."""

    utterances: list[RawUtterance]
    language: str
    asr_provider: str
    asr_model: str
    asr_model_version: str
    diarization_provider: str
    diarization_version: str
    transcription_config_hash: str
    diarization_config_hash: str
    processing_mode: str = "live_asr"  # "live_asr" | "fixture_replay"


class TranscriptionPort(ABC):
    """Abstract interface for ASR and speaker diarization providers."""

    @abstractmethod
    async def transcribe(self, source: AudioSource) -> TranscriptionResult:
        """Convert bounded audio file into timestamped utterances with speaker labels."""

    @abstractmethod
    def provider_name(self) -> str:
        """Return provider identifier (e.g. 'deterministic-benchmark', 'faster-whisper')."""
