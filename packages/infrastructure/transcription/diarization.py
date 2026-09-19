"""Speaker diarization strategies for turning ASR utterances into speaker-attributed turns.

Dialler recordings are normally captured with the agent and the customer on separate channels. When
that is true, channel separation is exact and needs no model: each utterance is attributed to
whichever channel carried the energy while it was spoken.

When the audio is mono, no diarization is performed. The result says so honestly via
``diarization_provider="none"`` and ``is_diarized=False`` rather than labelling every utterance as
one speaker and implying speaker separation happened. Callers must treat an undiarised transcript
as unsafe for speaker-scoped compliance checks.
"""

import array
import hashlib
import wave
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from packages.application.ports.transcription import RawUtterance
from packages.observability.logging import get_logger

logger = get_logger("transcription.diarization")

# Energy profile resolution. 50 ms is far finer than any utterance boundary while keeping the
# pure-Python scan cheap on a 30-minute call.
_WINDOW_MS = 50
_MAX_SAMPLES_PER_WINDOW = 32

CHANNEL_SPEAKER_LABELS = ("SPEAKER_CH0", "SPEAKER_CH1")
UNDIARIZED_SPEAKER_LABEL = "SPEAKER_UNKNOWN"


@dataclass(frozen=True)
class DiarizationOutcome:
    """Utterances with speaker labels applied, plus provenance of how they were derived."""

    utterances: list[RawUtterance]
    provider: str
    version: str
    config_hash: str
    is_diarized: bool
    speaker_count: int
    reason_codes: list[str]


class DiarizerPort(ABC):
    """Assigns speaker labels to ASR utterances."""

    @abstractmethod
    def diarize(
        self, audio_path: str, utterances: Sequence[RawUtterance]
    ) -> DiarizationOutcome:
        """Attribute each utterance to a speaker."""


# ======================================================================================
# Per-channel energy profiling
# ======================================================================================


@dataclass(frozen=True)
class ChannelEnergyProfile:
    """Mean absolute amplitude per channel, sampled on a fixed millisecond grid."""

    window_ms: int
    channels: int
    # energy[channel][window_index]
    energy: list[list[float]]

    def dominant_channel(self, start_ms: int, end_ms: int) -> tuple[int | None, float]:
        """Return the louder channel over a span and how decisively it leads.

        The margin is the leading channel's share of total energy in the span (0.5 means the two
        channels are indistinguishable, 1.0 means all energy sat on one channel).
        """
        first = max(0, start_ms // self.window_ms)
        last = max(first + 1, min(len(self.energy[0]), (end_ms // self.window_ms) + 1))

        totals = [sum(channel[first:last]) for channel in self.energy]
        grand_total = sum(totals)
        if grand_total <= 0:
            return None, 0.0

        leader = max(range(len(totals)), key=lambda index: totals[index])
        return leader, totals[leader] / grand_total


def build_channel_energy_profile(audio_path: str) -> ChannelEnergyProfile | None:
    """Build a per-channel energy profile from a PCM WAV file, or None if unreadable."""
    try:
        with wave.open(audio_path, "rb") as wav:
            channels = wav.getnchannels()
            sample_rate = wav.getframerate()
            sample_width = wav.getsampwidth()
            frame_count = wav.getnframes()

            if sample_width != 2:
                # Only 16-bit PCM is profiled; other widths fall through to no diarization.
                logger.info("diarization_unsupported_sample_width", sample_width=sample_width)
                return None

            frames_per_window = max(1, (sample_rate * _WINDOW_MS) // 1000)
            stride = max(1, frames_per_window // _MAX_SAMPLES_PER_WINDOW)

            energy: list[list[float]] = [[] for _ in range(channels)]
            remaining = frame_count

            while remaining > 0:
                take = min(frames_per_window, remaining)
                raw = wav.readframes(take)
                if not raw:
                    break
                remaining -= take

                samples = array.array("h")
                samples.frombytes(raw)

                for channel in range(channels):
                    total = 0
                    count = 0
                    for index in range(channel, len(samples), channels * stride):
                        total += abs(samples[index])
                        count += 1
                    energy[channel].append(total / count if count else 0.0)

            return ChannelEnergyProfile(
                window_ms=_WINDOW_MS, channels=channels, energy=energy
            )
    except (wave.Error, EOFError, OSError, ValueError) as exc:
        logger.info("diarization_energy_profile_failed", error=str(exc))
        return None


# ======================================================================================
# Diarizers
# ======================================================================================


class StereoChannelDiarizer(DiarizerPort):
    """Attributes utterances by which recorded channel carried them.

    Exact where the dialler records each party on its own channel. Where the channels bleed into
    each other the margin falls toward 0.5; utterances below ``min_margin`` are left unattributed
    so downstream role resolution treats them as uncertain rather than guessing.
    """

    version = "stereo-channel-v1"

    def __init__(self, min_margin: float = 0.62):
        self.min_margin = min_margin
        self.config_hash = hashlib.sha256(
            f"{self.version}:{_WINDOW_MS}:{min_margin}".encode()
        ).hexdigest()[:16]

    def diarize(
        self, audio_path: str, utterances: Sequence[RawUtterance]
    ) -> DiarizationOutcome:
        profile = build_channel_energy_profile(audio_path)

        if profile is None or profile.channels < 2:
            return _undiarized(
                utterances,
                reason="AUDIO_NOT_MULTICHANNEL" if profile else "AUDIO_PROFILE_UNAVAILABLE",
            )

        labelled: list[RawUtterance] = []
        unattributed = 0
        seen_labels: set[str] = set()

        for utterance in utterances:
            channel, margin = profile.dominant_channel(utterance.start_ms, utterance.end_ms)
            if channel is None or margin < self.min_margin:
                label = UNDIARIZED_SPEAKER_LABEL
                unattributed += 1
            else:
                label = (
                    CHANNEL_SPEAKER_LABELS[channel]
                    if channel < len(CHANNEL_SPEAKER_LABELS)
                    else f"SPEAKER_CH{channel}"
                )
                seen_labels.add(label)

            labelled.append(
                RawUtterance(
                    speaker_label=label,
                    start_ms=utterance.start_ms,
                    end_ms=utterance.end_ms,
                    text=utterance.text,
                    words=utterance.words,
                )
            )

        reason_codes: list[str] = []
        if unattributed:
            reason_codes.append("SOME_UTTERANCES_UNATTRIBUTED")
        if len(seen_labels) < 2:
            reason_codes.append("SINGLE_SPEAKER_DETECTED")

        logger.info(
            "stereo_diarization_complete",
            utterances=len(labelled),
            unattributed=unattributed,
            speakers=len(seen_labels),
        )

        return DiarizationOutcome(
            utterances=labelled,
            provider="stereo-channel",
            version=self.version,
            config_hash=self.config_hash,
            is_diarized=len(seen_labels) >= 2,
            speaker_count=len(seen_labels),
            reason_codes=reason_codes,
        )


class PyannoteDiarizer(DiarizerPort):
    """Model-based diarization for mono recordings, used when pyannote.audio is installed."""

    version = "pyannote-3.1"

    def __init__(self, model_name: str = "pyannote/speaker-diarization-3.1", auth_token: str | None = None):
        self.model_name = model_name
        self.auth_token = auth_token
        self.config_hash = hashlib.sha256(f"{self.version}:{model_name}".encode()).hexdigest()[:16]

    def diarize(
        self, audio_path: str, utterances: Sequence[RawUtterance]
    ) -> DiarizationOutcome:
        try:
            from pyannote.audio import Pipeline
        except ImportError:
            logger.info("pyannote_not_installed_falling_back")
            return _undiarized(utterances, reason="DIARIZATION_PROVIDER_UNAVAILABLE")

        pipeline = Pipeline.from_pretrained(self.model_name, use_auth_token=self.auth_token)
        annotation = pipeline(audio_path)

        turns = [
            (int(segment.start * 1000), int(segment.end * 1000), str(speaker))
            for segment, _, speaker in annotation.itertracks(yield_label=True)
        ]

        labelled: list[RawUtterance] = []
        seen_labels: set[str] = set()
        unattributed = 0

        for utterance in utterances:
            label = _best_overlapping_turn(turns, utterance.start_ms, utterance.end_ms)
            if label is None:
                label = UNDIARIZED_SPEAKER_LABEL
                unattributed += 1
            else:
                seen_labels.add(label)
            labelled.append(
                RawUtterance(
                    speaker_label=label,
                    start_ms=utterance.start_ms,
                    end_ms=utterance.end_ms,
                    text=utterance.text,
                    words=utterance.words,
                )
            )

        reason_codes = ["SOME_UTTERANCES_UNATTRIBUTED"] if unattributed else []
        if len(seen_labels) < 2:
            reason_codes.append("SINGLE_SPEAKER_DETECTED")

        return DiarizationOutcome(
            utterances=labelled,
            provider="pyannote",
            version=self.version,
            config_hash=self.config_hash,
            is_diarized=len(seen_labels) >= 2,
            speaker_count=len(seen_labels),
            reason_codes=reason_codes,
        )


class CompositeDiarizer(DiarizerPort):
    """Tries each diarizer in order and returns the first that actually separates speakers."""

    def __init__(self, diarizers: Sequence[DiarizerPort]):
        self._diarizers = list(diarizers)
        self.config_hash = hashlib.sha256(
            ":".join(type(d).__name__ for d in self._diarizers).encode()
        ).hexdigest()[:16]

    def diarize(
        self, audio_path: str, utterances: Sequence[RawUtterance]
    ) -> DiarizationOutcome:
        outcome = _undiarized(utterances, reason="NO_DIARIZER_CONFIGURED")
        for diarizer in self._diarizers:
            try:
                outcome = diarizer.diarize(audio_path, utterances)
            except Exception as exc:  # A diarizer failing must not fail the transcription job.
                logger.warning(
                    "diarizer_failed", diarizer=type(diarizer).__name__, error=str(exc)
                )
                continue
            if outcome.is_diarized:
                return outcome
        return outcome


def _best_overlapping_turn(
    turns: Sequence[tuple[int, int, str]], start_ms: int, end_ms: int
) -> str | None:
    """Return the speaker whose turn overlaps the span the most."""
    best_label: str | None = None
    best_overlap = 0
    for turn_start, turn_end, label in turns:
        overlap = min(end_ms, turn_end) - max(start_ms, turn_start)
        if overlap > best_overlap:
            best_overlap = overlap
            best_label = label
    return best_label


def _undiarized(utterances: Sequence[RawUtterance], reason: str) -> DiarizationOutcome:
    """Return utterances with no speaker attribution, labelled honestly as such."""
    return DiarizationOutcome(
        utterances=[
            RawUtterance(
                speaker_label=UNDIARIZED_SPEAKER_LABEL,
                start_ms=u.start_ms,
                end_ms=u.end_ms,
                text=u.text,
                words=u.words,
            )
            for u in utterances
        ],
        provider="none",
        version="n/a",
        config_hash="0" * 16,
        is_diarized=False,
        speaker_count=0,
        reason_codes=[reason],
    )
