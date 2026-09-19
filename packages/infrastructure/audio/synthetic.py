"""Generates channel-accurate placeholder audio for demos and pipeline tests.

What this produces is **not speech**. It is real 16-bit PCM whose energy is placed on the correct
channel at the correct moment for each turn, which is exactly what the ingestion pipeline, the WAV
inspector and the channel diarizer need in order to be exercised for real rather than against a
byte string like ``b"MOCK_WAV_AUDIO"``.

It is deliberately useless for ASR: running Whisper over it yields nothing, because there are no
words in it. Measuring transcription accuracy requires a genuine recording — see
``docs/scoring-accuracy.md``.
"""

import math
import wave
from array import array
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO

DEFAULT_SAMPLE_RATE = 8000
DEFAULT_AMPLITUDE = 11000

# Two pitches so the channels are distinguishable by ear as well as by energy.
AGENT_TONE_HZ = 210.0
CUSTOMER_TONE_HZ = 330.0


@dataclass(frozen=True)
class AudioTurn:
    """One party speaking between two timestamps, on their own channel."""

    channel: int
    start_ms: int
    end_ms: int


def build_turns_from_segments(
    segments: Sequence[object],
    agent_role: str = "AGENT",
) -> list[AudioTurn]:
    """Map transcript segments onto per-channel turns: agent on channel 0, customer on channel 1."""
    turns: list[AudioTurn] = []
    for segment in segments:
        role = getattr(segment, "business_role", None)
        role_value = getattr(role, "value", role)
        turns.append(
            AudioTurn(
                channel=0 if str(role_value) == agent_role else 1,
                start_ms=int(getattr(segment, "start_ms", 0)),
                end_ms=int(getattr(segment, "end_ms", 0)),
            )
        )
    return turns


def synthesize_stereo_wav(
    turns: Sequence[AudioTurn],
    duration_ms: int | None = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = 2,
    amplitude: int = DEFAULT_AMPLITUDE,
) -> bytes:
    """Render turns as a WAV file where each turn's energy sits only on its own channel.

    A brief fade is applied at each turn boundary so the waveform has no discontinuities, which
    would otherwise show up as clicks and distort energy measurement at the edges.
    """
    if duration_ms is None:
        duration_ms = max((turn.end_ms for turn in turns), default=1000)

    total_frames = max(1, int(sample_rate * duration_ms / 1000))
    fade_frames = max(1, sample_rate // 200)  # 5 ms
    tones = [AGENT_TONE_HZ, CUSTOMER_TONE_HZ]

    # One period per tone is computed once and tiled. A 30-minute call is tens of millions of
    # samples; generating each one through math.sin in Python takes minutes, and tiling a cached
    # period reduces that to about a second.
    periods: dict[float, list[int]] = {}
    for frequency in tones[:channels]:
        period_length = max(1, round(sample_rate / frequency))
        periods[frequency] = [
            int(amplitude * math.sin(2 * math.pi * index / period_length))
            for index in range(period_length)
        ]

    frames = array("h", bytes(2 * total_frames * channels))

    for turn in turns:
        if turn.channel >= channels or turn.end_ms <= turn.start_ms:
            continue
        start_frame = max(0, int(turn.start_ms * sample_rate / 1000))
        end_frame = min(total_frames, int(turn.end_ms * sample_rate / 1000))
        span = end_frame - start_frame
        if span <= 0:
            continue

        period = periods[tones[turn.channel % len(tones)]]
        repeats = span // len(period) + 1
        tone = (period * repeats)[:span]

        # Fade the edges so turn boundaries carry no discontinuity, which would read as a click
        # and skew the energy measurement the diarizer takes at the edges.
        edge = min(fade_frames, span // 2)
        for index in range(edge):
            scale = index / edge
            tone[index] = int(tone[index] * scale)
            tone[span - 1 - index] = int(tone[span - 1 - index] * scale)

        frames[start_frame * channels + turn.channel : end_frame * channels + turn.channel : channels] = array("h", tone)

    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(frames.tobytes())
    return buffer.getvalue()


def synthesize_from_segments(
    segments: Sequence[object],
    duration_ms: int | None = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> bytes:
    """Convenience wrapper: transcript segments in, a two-channel WAV out."""
    return synthesize_stereo_wav(
        turns=build_turns_from_segments(segments),
        duration_ms=duration_ms,
        sample_rate=sample_rate,
    )
