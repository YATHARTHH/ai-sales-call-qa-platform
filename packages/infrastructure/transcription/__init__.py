"""Transcription adapters and role resolvers."""

from packages.infrastructure.transcription.deterministic_adapter import (
    DeterministicTranscriptionAdapter,
)
from packages.infrastructure.transcription.role_resolver import (
    HeuristicSpeakerRoleResolver,
)
from packages.infrastructure.transcription.whisper_adapter import (
    FasterWhisperAdapter,
    ProviderConfigurationError,
)

__all__ = [
    "DeterministicTranscriptionAdapter",
    "HeuristicSpeakerRoleResolver",
    "FasterWhisperAdapter",
    "ProviderConfigurationError",
]
