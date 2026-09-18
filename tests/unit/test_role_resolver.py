"""Unit tests for heuristic speaker role resolution and fallback logic."""

from packages.application.ports.role_resolver import SpeakerProfile
from packages.domain.transcript import SpeakerType
from packages.infrastructure.transcription.role_resolver import (
    HeuristicSpeakerRoleResolver,
)


def test_role_resolver_maps_agent_and_customer():
    resolver = HeuristicSpeakerRoleResolver()

    profiles = [
        SpeakerProfile(
            speaker_label="SPEAKER_00",
            total_utterances=15,
            first_spoken_ms=1000,
            total_speech_ms=45000,
            sample_text="Hello thank you for calling Energy Comparison Services. My name is Sarah.",
        ),
        SpeakerProfile(
            speaker_label="SPEAKER_01",
            total_utterances=12,
            first_spoken_ms=6000,
            total_speech_ms=30000,
            sample_text="Hi Sarah, I am looking to compare electricity plans for my home.",
        ),
    ]

    mapping = resolver.resolve(profiles)
    assert mapping.get_role("SPEAKER_00") == SpeakerType.AGENT
    assert mapping.get_role("SPEAKER_01") == SpeakerType.CUSTOMER
    assert mapping.mappings["SPEAKER_00"].confidence >= 0.7
    assert mapping.mappings["SPEAKER_01"].confidence >= 0.7


def test_role_resolver_falls_back_to_unknown_for_ambiguous_speakers():
    """When speech lacks greeting or domain clues, falls back to SpeakerType.UNKNOWN."""
    resolver = HeuristicSpeakerRoleResolver(confidence_threshold=0.7)

    profiles = [
        SpeakerProfile(
            speaker_label="SPEAKER_02",
            total_utterances=1,
            first_spoken_ms=50000,
            total_speech_ms=1000,
            sample_text="Mmhmm yeah.",
        ),
    ]

    mapping = resolver.resolve(profiles)
    assert mapping.get_role("SPEAKER_02") == SpeakerType.UNKNOWN
    assert mapping.mappings["SPEAKER_02"].confidence < 0.7
