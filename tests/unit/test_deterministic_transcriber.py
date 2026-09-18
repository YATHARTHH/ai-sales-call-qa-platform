"""Synthetic Integration Benchmark tests for DeterministicTranscriptionAdapter.

Note: Validates pipeline wiring, serialization, role mapping, speech metrics,
idempotency, provenance, and API behavior. Does NOT evaluate real acoustic ASR accuracy.
"""

import os
import tempfile

import pytest

from packages.application.ports.transcription import AudioSource
from packages.infrastructure.transcription.deterministic_adapter import (
    DeterministicTranscriptionAdapter,
)


@pytest.mark.asyncio
async def test_deterministic_benchmark_loads_fixture_accurately():
    """Validates that DeterministicTranscriptionAdapter accurately maps CIMET Brief 1 events."""
    adapter = DeterministicTranscriptionAdapter()

    # Create dummy local file to satisfy AudioSource contract
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(b"RIFF" + b"\x00" * 500)
        temp_path = f.name

    try:
        source = AudioSource(
            local_path=temp_path,
            content_hash="mock-sha256",
            mime_type="audio/wav",
            size_bytes=504,
        )
        result = await adapter.transcribe(source)

        assert result.asr_provider == "deterministic"
        assert result.processing_mode == "fixture_replay"
        assert len(result.utterances) >= 8

        # 1. Rate mismatch at 14:02 (842,000 ms)
        rate_utt = next((u for u in result.utterances if u.start_ms == 842000), None)
        assert rate_utt is not None
        assert "28.6 cents per kilowatt hour" in rate_utt.text

        # 2. Dead air hold before 18:30 (1,110,000 ms to 1,157,000 ms)
        hold_utt = next((u for u in result.utterances if u.start_ms == 1105000), None)
        resume_utt = next((u for u in result.utterances if u.start_ms == 1157000), None)
        assert hold_utt is not None and resume_utt is not None
        gap_ms = resume_utt.start_ms - hold_utt.end_ms
        assert gap_ms == 47000  # Exactly 47 seconds of dead air

        # 3. Spoken email typo at 22:10 (1,330,000 ms)
        email_utt = next((u for u in result.utterances if u.start_ms == 1330000), None)
        assert email_utt is not None
        assert "john.smith@gmial.com" in email_utt.text

        # 4. Mandatory disclosures at 25:00 (1,500,000 ms)
        disclosure_utt = next((u for u in result.utterances if u.start_ms == 1500000), None)
        assert disclosure_utt is not None
        assert "10 business day cooling off period" in disclosure_utt.text
        assert "explicit informed consent" in disclosure_utt.text
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
