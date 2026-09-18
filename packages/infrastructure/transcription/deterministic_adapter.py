"""Deterministic synthetic benchmark adapter for transcription and speaker diarization.

Validates the AudioSource input contract and emits predictable, canonical utterances
without executing GPU/acoustic model inference. Used for reliable pipeline tests and local benchmark runs.
"""

import hashlib
import json
import os
from pathlib import Path

from packages.application.ports.transcription import (
    AudioSource,
    RawUtterance,
    TranscriptionPort,
    TranscriptionResult,
    WordTiming,
)
from packages.domain.exceptions import ArtifactIntegrityError
from packages.observability.logging import get_logger

logger = get_logger("transcription.deterministic")

DEFAULT_BENCHMARK_FIXTURE = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "tests"
    / "fixtures"
    / "transcription"
    / "lead_3613790_benchmark.json"
)


class DeterministicTranscriptionAdapter(TranscriptionPort):
    """Synthetic benchmark adapter reading scenario fixtures with zero cloud API costs."""

    def __init__(self, fixture_path: str | Path | None = None):
        self.fixture_path = Path(fixture_path or DEFAULT_BENCHMARK_FIXTURE)
        self.transcription_config_hash = hashlib.sha256(b"deterministic-asr-config-v1").hexdigest()[:16]
        self.diarization_config_hash = hashlib.sha256(b"deterministic-diarize-config-v1").hexdigest()[:16]

    def provider_name(self) -> str:
        return "deterministic-benchmark"

    async def transcribe(self, source: AudioSource) -> TranscriptionResult:
        """Validate AudioSource contract and return canonical benchmark utterances."""
        # 1. Enforce AudioSource contract
        if not source.local_path or not os.path.exists(source.local_path):
            raise ArtifactIntegrityError(f"AudioSource file not found at: '{source.local_path}'")

        if source.size_bytes <= 0:
            raise ArtifactIntegrityError(f"AudioSource file size is zero or invalid: {source.size_bytes}")

        if not source.content_hash:
            raise ArtifactIntegrityError("AudioSource content_hash must not be empty.")

        # 2. Load fixture data
        if not self.fixture_path.exists():
            raise FileNotFoundError(f"Synthetic benchmark fixture not found at '{self.fixture_path}'")

        with open(self.fixture_path, encoding="utf-8") as f:
            data = json.load(f)

        utterances: list[RawUtterance] = []
        for u in data.get("utterances", []):
            words = [
                WordTiming(
                    word=w["word"],
                    start_ms=w["start_ms"],
                    end_ms=w["end_ms"],
                    confidence=w.get("confidence"),
                )
                for w in u.get("words", [])
            ]
            utterances.append(
                RawUtterance(
                    speaker_label=u["speaker_label"],
                    start_ms=u["start_ms"],
                    end_ms=u["end_ms"],
                    text=u["text"],
                    words=words,
                )
            )

        logger.info(
            "deterministic_transcription_completed",
            scenario=data.get("benchmark_scenario", "unknown"),
            utterances_count=len(utterances),
            processing_mode="fixture_replay",
        )

        return TranscriptionResult(
            utterances=utterances,
            language=data.get("metadata", {}).get("language", "en-AU"),
            asr_provider="deterministic",
            asr_model="synthetic-benchmark",
            asr_model_version="benchmark-v1",
            diarization_provider="deterministic",
            diarization_version="benchmark-v1",
            transcription_config_hash=self.transcription_config_hash,
            diarization_config_hash=self.diarization_config_hash,
            processing_mode="fixture_replay",
        )
