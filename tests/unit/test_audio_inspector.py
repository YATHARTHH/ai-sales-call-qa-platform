"""Unit tests for native WAV audio inspector."""

import io
import os
import tempfile
import wave

import pytest

from packages.domain.exceptions import DomainError
from packages.infrastructure.audio.wav_inspector import WavAudioInspector


def create_wav_bytes(
    duration_seconds: float = 1.0,
    sample_rate: int = 16000,
    channels: int = 1,
    bit_depth: int = 16,
) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(bit_depth // 8)
        wf.setframerate(sample_rate)
        num_frames = int(sample_rate * duration_seconds)
        wf.writeframes(b"\x00" * (num_frames * channels * (bit_depth // 8)))
    return buf.getvalue()


def test_inspect_valid_wav_pcm_16k_mono():
    inspector = WavAudioInspector()
    wav_bytes = create_wav_bytes(duration_seconds=2.5, sample_rate=16000, channels=1, bit_depth=16)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(wav_bytes)
        tmp.flush()
        tmp_path = tmp.name
    try:
        meta = inspector.inspect_file(tmp_path)
        assert meta.channels == 1
        assert meta.sample_rate == 16000
        assert meta.bit_depth == 16
        assert meta.format_name == "WAV"
        assert abs(meta.duration_seconds - 2.5) < 0.01
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_inspect_valid_wav_pcm_8k_stereo():
    inspector = WavAudioInspector()
    wav_bytes = create_wav_bytes(duration_seconds=1.2, sample_rate=8000, channels=2, bit_depth=16)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(wav_bytes)
        tmp.flush()
        tmp_path = tmp.name
    try:
        meta = inspector.inspect_file(tmp_path)
        assert meta.channels == 2
        assert meta.sample_rate == 8000
        assert abs(meta.duration_seconds - 1.2) < 0.01
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_inspect_rejects_empty_file():
    inspector = WavAudioInspector()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp_path = tmp.name
    try:
        with pytest.raises(DomainError) as exc_info:
            inspector.inspect_file(tmp_path)
        assert exc_info.value.code == "EMPTY_AUDIO_FILE"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_inspect_rejects_corrupt_header():
    inspector = WavAudioInspector()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(b"NOT_A_VALID_RIFF_HEADER_1234567890")
        tmp.flush()
        tmp_path = tmp.name
    try:
        with pytest.raises(DomainError) as exc_info:
            inspector.inspect_file(tmp_path)
        assert exc_info.value.code == "INVALID_AUDIO_FORMAT"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_inspect_rejects_short_duration():
    inspector = WavAudioInspector()
    wav_bytes = create_wav_bytes(duration_seconds=0.2, sample_rate=16000)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(wav_bytes)
        tmp.flush()
        tmp_path = tmp.name
    try:
        with pytest.raises(DomainError) as exc_info:
            inspector.inspect_file(tmp_path)
        assert exc_info.value.code == "AUDIO_DURATION_TOO_SHORT"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
