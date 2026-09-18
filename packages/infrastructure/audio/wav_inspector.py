"""WAV / PCM audio inspector implementation using native Python wave module."""

import os
import wave
from typing import BinaryIO

from packages.application.ports.audio import AudioInspectorPort, AudioMetadata
from packages.domain.exceptions import DomainError


class WavAudioInspector(AudioInspectorPort):
    """Inspects and validates PCM WAV audio files and streams without external dependencies."""

    MIN_DURATION_SECONDS: float = 0.5
    SUPPORTED_SAMPLE_RATES: set[int] = {8000, 11025, 16000, 22050, 32000, 44100, 48000, 96000}

    def inspect_file(self, file_path: str) -> AudioMetadata:
        if not os.path.exists(file_path):
            raise DomainError(
                f"Audio file does not exist: {file_path}", code="AUDIO_FILE_NOT_FOUND"
            )

        size_bytes = os.path.getsize(file_path)
        if size_bytes == 0:
            raise DomainError("Audio file is empty (0 bytes)", code="EMPTY_AUDIO_FILE")

        try:
            with wave.open(file_path, "rb") as wav_file:
                return self._extract_metadata(wav_file, size_bytes)
        except wave.Error as exc:
            raise DomainError(
                f"Invalid WAV audio container: {exc}", code="INVALID_AUDIO_FORMAT"
            ) from exc
        except EOFError as exc:
            raise DomainError(
                f"Truncated WAV audio file: {exc}", code="INVALID_AUDIO_FORMAT"
            ) from exc

    def inspect_stream(self, stream: BinaryIO, size_bytes: int) -> AudioMetadata:
        if size_bytes == 0:
            raise DomainError("Audio stream is empty (0 bytes)", code="EMPTY_AUDIO_FILE")

        try:
            with wave.open(stream, "rb") as wav_file:
                return self._extract_metadata(wav_file, size_bytes)
        except wave.Error as exc:
            raise DomainError(
                f"Invalid WAV audio container: {exc}", code="INVALID_AUDIO_FORMAT"
            ) from exc
        except EOFError as exc:
            raise DomainError(
                f"Truncated WAV audio stream: {exc}", code="INVALID_AUDIO_FORMAT"
            ) from exc

    def _extract_metadata(self, wav_file: wave.Wave_read, size_bytes: int) -> AudioMetadata:
        channels = wav_file.getnchannels()
        sample_rate = wav_file.getframerate()
        sample_width = wav_file.getsampwidth()
        num_frames = wav_file.getnframes()

        if sample_rate == 0:
            raise DomainError(
                "Invalid WAV audio: sample rate cannot be zero", code="INVALID_AUDIO_FORMAT"
            )

        duration_seconds = num_frames / float(sample_rate)

        if duration_seconds < self.MIN_DURATION_SECONDS:
            raise DomainError(
                f"Audio duration ({duration_seconds:.2f}s) is below minimum required duration ({self.MIN_DURATION_SECONDS}s)",
                code="AUDIO_DURATION_TOO_SHORT",
            )

        return AudioMetadata(
            duration_seconds=round(duration_seconds, 3),
            channels=channels,
            sample_rate=sample_rate,
            bit_depth=sample_width * 8,
            format_name="WAV",
            num_frames=num_frames,
            size_bytes=size_bytes,
        )
