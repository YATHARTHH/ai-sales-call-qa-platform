"""Transcription port contract for Speech-to-Text / Diarization engines."""

from abc import ABC, abstractmethod
from typing import Any


class TranscriptionPort(ABC):
    """Abstract interface for ASR and speaker diarization providers."""

    @abstractmethod
    async def transcribe(self, audio_data: bytes, mime_type: str) -> dict[str, Any]:
        """Convert speech audio into a timestamped transcript."""

    @abstractmethod
    def provider_name(self) -> str:
        """Return provider identifier (e.g. 'whisper-local', 'deepgram')."""
