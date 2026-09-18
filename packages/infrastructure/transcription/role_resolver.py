"""Rule-based heuristic implementation of SpeakerRoleResolverPort."""

import re
from typing import Any

from packages.application.ports.role_resolver import (
    RoleAssignment,
    SpeakerProfile,
    SpeakerRoleMapping,
    SpeakerRoleResolverPort,
)
from packages.domain.transcript import SpeakerType
from packages.observability.logging import get_logger

logger = get_logger("transcription.role_resolver")

AGENT_PHRASES = [
    r"thank\s+you\s+for\s+calling",
    r"thanks\s+for\s+calling",
    r"my\s+name\s+is",
    r"how\s+can\s+i\s+help",
    r"energy\s+comparison",
    r"cooling\s*off\s+period",
    r"explicit\s+informed\s+consent",
    r"water\s+ombudsman",
    r"welcome\s+pack",
    r"assist\s+you",
]

CUSTOMER_PHRASES = [
    r"looking\s+to\s+compare",
    r"my\s+home",
    r"compare\s+rates",
    r"electricity\s+plans",
    r"bill",
    r"tariff",
]


class HeuristicSpeakerRoleResolver(SpeakerRoleResolverPort):
    """Conservative lexical and turn-order heuristic role resolver."""

    def __init__(self, confidence_threshold: float = 0.7):
        self.confidence_threshold = confidence_threshold
        self.role_mapping_version = "heuristic-v1"

    def resolve(
        self, speakers: list[SpeakerProfile], context: dict[str, Any] | None = None
    ) -> SpeakerRoleMapping:
        """Resolve speaker roles based on greeting cues, lexical matching, and turn order."""
        if not speakers:
            return SpeakerRoleMapping(mappings={}, role_mapping_version=self.role_mapping_version)

        # Sort profiles deterministically
        sorted_speakers = sorted(speakers, key=lambda s: s.first_spoken_ms)
        mappings: dict[str, RoleAssignment] = {}

        # First speaker in outbound/inbound sales call is typically the agent
        first_speaker_label = sorted_speakers[0].speaker_label

        for profile in sorted_speakers:
            agent_score = 0.0
            customer_score = 0.0
            text_lower = profile.sample_text.lower()

            # First speaker bonus
            if profile.speaker_label == first_speaker_label:
                agent_score += 0.4

            # Lexical match score
            for pattern in AGENT_PHRASES:
                if re.search(pattern, text_lower):
                    agent_score += 0.3

            for pattern in CUSTOMER_PHRASES:
                if re.search(pattern, text_lower):
                    customer_score += 0.3

            # Determine role with conservative confidence
            if agent_score >= customer_score:
                conf = min(1.0, agent_score)
                if conf >= self.confidence_threshold:
                    role = SpeakerType.AGENT
                    reason = "GREETING_AND_AGENT_LEXICAL_MATCH"
                else:
                    role = SpeakerType.UNKNOWN
                    reason = "LOW_CONFIDENCE_AGENT_MATCH"
            else:
                conf = min(1.0, customer_score)
                if conf >= self.confidence_threshold:
                    role = SpeakerType.CUSTOMER
                    reason = "CUSTOMER_LEXICAL_MATCH"
                else:
                    role = SpeakerType.UNKNOWN
                    reason = "LOW_CONFIDENCE_CUSTOMER_MATCH"

            mappings[profile.speaker_label] = RoleAssignment(
                business_role=role,
                confidence=round(conf, 2),
                resolution_method="lexical_turn_heuristic",
                reason_code=reason,
            )

        # Ensure sorted dict
        deterministic_mappings = dict(sorted(mappings.items()))

        logger.info(
            "speaker_roles_resolved",
            mappings={k: v.business_role.value for k, v in deterministic_mappings.items()},
        )

        return SpeakerRoleMapping(
            mappings=deterministic_mappings,
            role_mapping_version=self.role_mapping_version,
        )
