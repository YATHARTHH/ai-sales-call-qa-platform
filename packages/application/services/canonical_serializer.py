"""Deterministic canonical transcript serializer for derived storage artifacts."""

import json
from typing import Any

from packages.application.ports.transcription import TranscriptionResult
from packages.domain.speech_metrics import SpeechBehaviorMetrics
from packages.domain.transcript import SpeakerType, Transcript


class CanonicalTranscriptSerializer:
    """Produces bit-for-bit reproducible JSON representations of transcripts."""

    SCHEMA_VERSION = "transcript.v1"

    @classmethod
    def serialize(
        cls,
        transcript: Transcript,
        result: TranscriptionResult,
        role_map: dict[str, Any],
        behavior: SpeechBehaviorMetrics,
    ) -> str:
        """Serialize transcript into a deterministic JSON string."""
        # 1. Deterministically order utterances
        sorted_utterances = sorted(
            result.utterances,
            key=lambda u: (u.start_ms, u.end_ms, u.speaker_label),
        )

        segments_data = []
        for i, u in enumerate(sorted_utterances):
            role = role_map.get(u.speaker_label)
            role_str = (
                role.business_role.value
                if hasattr(role, "business_role")
                else str(role or SpeakerType.UNKNOWN.value)
            )
            role_conf = (
                role.confidence if hasattr(role, "confidence") else 1.0
            )

            # Sort words inside utterance
            sorted_words = sorted(
                u.words,
                key=lambda w: (w.start_ms, w.end_ms, w.word),
            )
            words_data = [
                {
                    "word": w.word,
                    "start_ms": w.start_ms,
                    "end_ms": w.end_ms,
                    "confidence": round(w.confidence, 4) if w.confidence is not None else None,
                }
                for w in sorted_words
            ]

            segments_data.append({
                "segment_order": i + 1,
                "speaker_label": u.speaker_label,
                "business_role": role_str,
                "role_confidence": round(role_conf, 2),
                "start_ms": u.start_ms,
                "end_ms": u.end_ms,
                "text": u.text,
                "words": words_data,
            })

        # 2. Deterministically format speech behavior
        dead_air = [
            {"start_ms": g.start_ms, "end_ms": g.end_ms, "duration_ms": g.duration_ms}
            for g in sorted(behavior.dead_air_gaps, key=lambda g: (g.start_ms, g.end_ms))
        ]
        interruptions = [
            {
                "speaker_label": c.speaker_label,
                "interrupted_speaker_label": c.interrupted_speaker_label,
                "start_ms": c.start_ms,
                "overlap_duration_ms": c.overlap_duration_ms,
            }
            for c in sorted(behavior.interruption_candidates, key=lambda c: (c.start_ms, c.speaker_label))
        ]

        # 3. Assemble root dictionary
        canonical_doc = {
            "schema_version": cls.SCHEMA_VERSION,
            "transcription_key": transcript.transcription_key,
            "transcription_identity": transcript.transcription_identity,
            "availability": transcript.availability.value,
            "provenance": {
                "asr_provider": transcript.asr_provider,
                "asr_model": transcript.asr_model,
                "asr_model_version": transcript.asr_model_version,
                "diarization_provider": transcript.diarization_provider,
                "diarization_version": transcript.diarization_version,
                "processor_version": transcript.processor_version,
                "transcription_config_hash": transcript.transcription_config_hash,
                "diarization_config_hash": transcript.diarization_config_hash,
                "role_mapping_version": transcript.role_mapping_version,
                "language": transcript.language,
                "processing_mode": result.processing_mode,
            },
            "audio_coverage": {
                "audio_duration_ms": behavior.audio_duration_ms,
                "transcribed_coverage_end_ms": behavior.transcribed_coverage_end_ms,
                "leading_uncovered_ms": behavior.leading_uncovered_ms,
                "trailing_uncovered_ms": behavior.trailing_uncovered_ms,
                "has_uncovered_audio": behavior.has_uncovered_audio,
            },
            "speech_behavior": {
                "agent_talk_ms": behavior.agent_talk_ms,
                "customer_talk_ms": behavior.customer_talk_ms,
                "total_speech_ms": behavior.total_speech_ms,
                "agent_talk_percentage": behavior.agent_talk_percentage,
                "customer_talk_percentage": behavior.customer_talk_percentage,
                "conversational_occupancy_percentage": behavior.conversational_occupancy_percentage,
                "agent_words_per_minute": behavior.agent_words_per_minute,
                "customer_words_per_minute": behavior.customer_words_per_minute,
                "dead_air_gaps": dead_air,
                "interruption_candidates": interruptions,
            },
            "segments": segments_data,
        }

        return json.dumps(canonical_doc, sort_keys=True, indent=2, ensure_ascii=False)
