"""Builds the configured speech-to-text and diarization stack.

Provider choice is configuration, not code. The default is the deterministic adapter, which
replays a fixture and needs no model — so a clone of the repo runs the full pipeline with no
downloads. Setting ``ASR_PROVIDER=whisper`` swaps in live inference.
"""

from packages.application.ports.transcription import TranscriptionPort
from packages.infrastructure.config.settings import settings
from packages.infrastructure.transcription.deterministic_adapter import (
    DeterministicTranscriptionAdapter,
)
from packages.infrastructure.transcription.diarization import (
    CompositeDiarizer,
    DiarizerPort,
    PyannoteDiarizer,
    StereoChannelDiarizer,
)
from packages.observability.logging import get_logger

logger = get_logger("transcription.factory")


def build_diarizer(provider: str | None = None) -> DiarizerPort:
    """Build the diarization strategy named by configuration."""
    choice = (provider or settings.diarization_provider).strip().lower()

    if choice == "channel":
        return StereoChannelDiarizer()
    if choice == "pyannote":
        return PyannoteDiarizer(auth_token=settings.pyannote_auth_token)
    # "auto": channel separation is exact when the dialler records each party on its own
    # channel, so it is tried first; pyannote only has to handle mono recordings.
    return CompositeDiarizer(
        [StereoChannelDiarizer(), PyannoteDiarizer(auth_token=settings.pyannote_auth_token)]
    )


def build_transcriber(provider: str | None = None) -> TranscriptionPort:
    """Build the ASR adapter named by configuration.

    An unavailable provider is a configuration error and is raised, not silently downgraded: a
    pipeline that quietly swapped live ASR for a fixture would score real calls against replayed
    text without anyone noticing.
    """
    choice = (provider or settings.asr_provider).strip().lower()

    if choice in ("whisper", "faster-whisper"):
        # Imported lazily so the optional [speech] extra is not needed to import this module.
        from packages.infrastructure.transcription.whisper_adapter import FasterWhisperAdapter

        logger.info(
            "asr_provider_selected",
            provider="faster-whisper",
            model=settings.whisper_model_size,
            device=settings.whisper_device,
        )
        return FasterWhisperAdapter(
            model_size=settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            diarizer=build_diarizer(),
        )

    logger.info("asr_provider_selected", provider="deterministic")
    return DeterministicTranscriptionAdapter()
