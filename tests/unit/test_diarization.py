"""Unit tests for stereo-channel speaker diarization and its honest fallbacks."""

import math
import struct
import wave

import pytest

from packages.application.ports.transcription import RawUtterance
from packages.infrastructure.transcription.diarization import (
    UNDIARIZED_SPEAKER_LABEL,
    CompositeDiarizer,
    StereoChannelDiarizer,
    build_channel_energy_profile,
)

SAMPLE_RATE = 8000


def write_two_channel_wav(path, turns, duration_ms, channels=2):
    """Write a WAV where each turn puts a tone on exactly one channel.

    `turns` is a list of (start_ms, end_ms, channel_index).
    """
    total_frames = int(SAMPLE_RATE * duration_ms / 1000)
    frames = bytearray()

    for frame_index in range(total_frames):
        time_ms = frame_index * 1000 / SAMPLE_RATE
        active = next(
            (channel for start, end, channel in turns if start <= time_ms < end), None
        )
        samples = []
        for channel_index in range(channels):
            if active is not None and channel_index == active:
                value = int(12000 * math.sin(2 * math.pi * 300 * frame_index / SAMPLE_RATE))
            else:
                value = 0
            samples.append(value)
        frames.extend(struct.pack("<" + "h" * channels, *samples))

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(frames))
    return str(path)


@pytest.fixture
def stereo_call(tmp_path):
    """A four-turn call: agent on channel 0, customer on channel 1."""
    turns = [
        (0, 2000, 0),
        (2000, 4000, 1),
        (4000, 6000, 0),
        (6000, 8000, 1),
    ]
    path = write_two_channel_wav(tmp_path / "stereo.wav", turns, duration_ms=8000)
    utterances = [
        RawUtterance(speaker_label="", start_ms=0, end_ms=1900, text="Hello, my name is Sarah."),
        RawUtterance(speaker_label="", start_ms=2100, end_ms=3900, text="Hi, yes speaking."),
        RawUtterance(speaker_label="", start_ms=4100, end_ms=5900, text="The peak rate is 31.9."),
        RawUtterance(speaker_label="", start_ms=6100, end_ms=7900, text="That sounds fine."),
    ]
    return path, utterances


@pytest.fixture
def mono_call(tmp_path):
    turns = [(0, 4000, 0)]
    path = write_two_channel_wav(tmp_path / "mono.wav", turns, duration_ms=4000, channels=1)
    utterances = [
        RawUtterance(speaker_label="", start_ms=0, end_ms=1900, text="Hello."),
        RawUtterance(speaker_label="", start_ms=2100, end_ms=3900, text="Hi there."),
    ]
    return path, utterances


class TestEnergyProfile:
    def test_profile_captures_both_channels(self, stereo_call):
        path, _ = stereo_call
        profile = build_channel_energy_profile(path)

        assert profile is not None
        assert profile.channels == 2

    def test_dominant_channel_matches_the_speaking_party(self, stereo_call):
        path, _ = stereo_call
        profile = build_channel_energy_profile(path)

        channel_first_turn, margin_first = profile.dominant_channel(0, 1900)
        channel_second_turn, margin_second = profile.dominant_channel(2100, 3900)

        assert channel_first_turn == 0
        assert channel_second_turn == 1
        assert margin_first > 0.9
        assert margin_second > 0.9

    def test_silent_span_has_no_dominant_channel(self, tmp_path):
        path = write_two_channel_wav(tmp_path / "silence.wav", [], duration_ms=2000)
        profile = build_channel_energy_profile(path)

        channel, margin = profile.dominant_channel(0, 2000)

        assert channel is None
        assert margin == 0.0


class TestStereoChannelDiarizer:
    def test_separates_two_speakers_by_channel(self, stereo_call):
        path, utterances = stereo_call

        outcome = StereoChannelDiarizer().diarize(path, utterances)

        assert outcome.is_diarized is True
        assert outcome.speaker_count == 2
        assert outcome.provider == "stereo-channel"
        labels = [u.speaker_label for u in outcome.utterances]
        assert labels[0] == labels[2]
        assert labels[1] == labels[3]
        assert labels[0] != labels[1]

    def test_preserves_text_and_timings(self, stereo_call):
        path, utterances = stereo_call

        outcome = StereoChannelDiarizer().diarize(path, utterances)

        assert [u.text for u in outcome.utterances] == [u.text for u in utterances]
        assert [u.start_ms for u in outcome.utterances] == [u.start_ms for u in utterances]

    def test_mono_audio_is_reported_as_undiarized_not_single_speaker(self, mono_call):
        """The failure mode this replaces: labelling everything one speaker and implying success."""
        path, utterances = mono_call

        outcome = StereoChannelDiarizer().diarize(path, utterances)

        assert outcome.is_diarized is False
        assert outcome.provider == "none"
        assert "AUDIO_NOT_MULTICHANNEL" in outcome.reason_codes
        assert all(u.speaker_label == UNDIARIZED_SPEAKER_LABEL for u in outcome.utterances)

    def test_missing_audio_file_degrades_without_raising(self, stereo_call):
        _, utterances = stereo_call

        outcome = StereoChannelDiarizer().diarize("does-not-exist.wav", utterances)

        assert outcome.is_diarized is False
        assert len(outcome.utterances) == len(utterances)

    def test_diarization_is_reproducible(self, stereo_call):
        path, utterances = stereo_call
        diarizer = StereoChannelDiarizer()

        first = diarizer.diarize(path, utterances)
        second = diarizer.diarize(path, utterances)

        assert [u.speaker_label for u in first.utterances] == [
            u.speaker_label for u in second.utterances
        ]
        assert first.config_hash == second.config_hash


class TestCompositeDiarizer:
    def test_uses_first_strategy_that_actually_separates_speakers(self, stereo_call):
        path, utterances = stereo_call

        outcome = CompositeDiarizer([StereoChannelDiarizer()]).diarize(path, utterances)

        assert outcome.is_diarized is True

    def test_a_failing_strategy_does_not_break_transcription(self, stereo_call):
        path, utterances = stereo_call

        class ExplodingDiarizer(StereoChannelDiarizer):
            def diarize(self, audio_path, utterances):
                raise RuntimeError("model unavailable")

        outcome = CompositeDiarizer([ExplodingDiarizer(), StereoChannelDiarizer()]).diarize(
            path, utterances
        )

        assert outcome.is_diarized is True

    def test_returns_undiarized_when_every_strategy_fails(self, mono_call):
        path, utterances = mono_call

        outcome = CompositeDiarizer([StereoChannelDiarizer()]).diarize(path, utterances)

        assert outcome.is_diarized is False
