"""Audio inspection port definitions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import BinaryIO


@dataclass(frozen=True)
class AudioMetadata:
    """Strongly-typed metadata extracted from an audio file or stream."""

    duration_seconds: float
    channels: int
    sample_rate: int
    bit_depth: int
    format_name: str
    num_frames: int
    size_bytes: int


class AudioInspectorPort(ABC):
    """Abstract interface for inspecting and validating audio containers and streams."""

    @abstractmethod
    def inspect_file(self, file_path: str) -> AudioMetadata:
        """Inspect an on-disk audio file and return extracted audio metadata."""

    @abstractmethod
    def inspect_stream(self, stream: BinaryIO, size_bytes: int) -> AudioMetadata:
        """Inspect an open binary audio stream and return extracted audio metadata."""
