"""Rule-based resolution of diarized speaker labels into business roles.

Diarization says *which* speaker said each line; this decides *who* that speaker is. Compliance
checks are speaker-scoped — a disclosure must come from the agent, a concession confirmation from
the customer — so a wrong or missing role silently disables whole checks.

A two-party sales call is treated as a **binary assignment**, not as two independent
classifications. Scoring each speaker separately and hoping both clear a threshold leaves the
customer unlabelled whenever they only say "yes, that's right" — which is most calls. Instead the
most agent-like speaker is assigned AGENT and the other is, by construction, the customer.
"""

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

# Scripted, role-specific language an agent uses and a customer essentially never does.
AGENT_PHRASES = (
    r"thank\s+you\s+for\s+calling",
    r"thanks\s+for\s+calling",
    r"my\s+name\s+is",
    r"calling\s+on\s+behalf",
    r"how\s+can\s+i\s+help",
    r"energy\s+comparison",
    r"this\s+call\s+is\s+being\s+recorded",
    r"cooling\s*off\s+period",
    r"explicit\s+informed\s+consent",
    r"account\s+holder",
    r"life\s+support",
    r"welcome\s+pack",
    r"terms\s+and\s+conditions",
    r"can\s+i\s+confirm",
    r"per\s+kilowatt\s+hour",
    r"supply\s+charge",
    r"default\s+offer",
    r"reference\s+price",
    r"assist\s+you",
)

# Language that marks the answering party.
CUSTOMER_PHRASES = (
    r"\bspeaking\b",
    r"that'?s\s+right",
    r"that'?s\s+correct",
    r"looking\s+to\s+compare",
    r"my\s+home",
    r"my\s+bill",
    r"i\s+don'?t\s+have",
    r"sounds\s+good",
    r"no\s+thanks",
    r"not\s+interested",
)

AGENT_CUE_WEIGHT = 0.22
CUSTOMER_CUE_WEIGHT = 0.18
FIRST_SPEAKER_BONUS = 0.30
TALK_TIME_WEIGHT = 0.25


class HeuristicSpeakerRoleResolver(SpeakerRoleResolverPort):
    """Assigns business roles to diarized speakers using lexical, turn-order and talk-time cues."""

    def __init__(self, confidence_threshold: float = 0.55):
        self.confidence_threshold = confidence_threshold
        self.role_mapping_version = "heuristic-v2"

    def resolve(
        self, speakers: list[SpeakerProfile], context: dict[str, Any] | None = None
    ) -> SpeakerRoleMapping:
        if not speakers:
            return SpeakerRoleMapping(mappings={}, role_mapping_version=self.role_mapping_version)

        ordered = sorted(speakers, key=lambda s: (s.first_spoken_ms, s.speaker_label))
        scores = {p.speaker_label: self._agent_affinity(p, ordered) for p in ordered}

        if len(ordered) == 1:
            return self._single_speaker_mapping(ordered[0], scores)

        # Binary (or n-ary) assignment: the most agent-like speaker is the agent, everyone else is
        # a customer. Both roles therefore always exist on a multi-speaker call.
        agent_label = max(scores, key=lambda label: (scores[label], label))
        margin = self._margin(scores, agent_label)

        mappings: dict[str, RoleAssignment] = {}
        for profile in ordered:
            is_agent = profile.speaker_label == agent_label
            mappings[profile.speaker_label] = RoleAssignment(
                business_role=SpeakerType.AGENT if is_agent else SpeakerType.CUSTOMER,
                confidence=round(min(1.0, 0.5 + margin), 2),
                resolution_method="binary_role_assignment",
                reason_code=(
                    "HIGHEST_AGENT_AFFINITY" if is_agent else "ASSIGNED_BY_ELIMINATION"
                ),
            )

        deterministic = dict(sorted(mappings.items()))
        logger.info(
            "speaker_roles_resolved",
            mappings={k: v.business_role.value for k, v in deterministic.items()},
            agent_affinity={k: round(v, 2) for k, v in sorted(scores.items())},
            margin=round(margin, 2),
        )
        return SpeakerRoleMapping(
            mappings=deterministic, role_mapping_version=self.role_mapping_version
        )

    # ------------------------------------------------------------------

    def _agent_affinity(
        self, profile: SpeakerProfile, ordered: list[SpeakerProfile]
    ) -> float:
        """Score how agent-like a speaker is. Higher means more likely to be the agent."""
        text = profile.sample_text.lower()
        score = 0.0

        score += AGENT_CUE_WEIGHT * sum(
            1 for pattern in AGENT_PHRASES if re.search(pattern, text)
        )
        score -= CUSTOMER_CUE_WEIGHT * sum(
            1 for pattern in CUSTOMER_PHRASES if re.search(pattern, text)
        )

        # The agent opens a compliance call, because the disclosure has to come first.
        if profile.speaker_label == ordered[0].speaker_label:
            score += FIRST_SPEAKER_BONUS

        # Agents read scripts; customers answer. Talk-time share is a weak but real signal, and it
        # is the only one that still works when the transcript is too garbled for lexical cues.
        total_speech = sum(p.total_speech_ms for p in ordered) or 1
        score += TALK_TIME_WEIGHT * (profile.total_speech_ms / total_speech)

        return score

    def _margin(self, scores: dict[str, float], agent_label: str) -> float:
        """How decisively the chosen agent beat the runner-up, normalised to roughly 0-0.5."""
        others = [value for label, value in scores.items() if label != agent_label]
        if not others:
            return 0.5
        gap = scores[agent_label] - max(others)
        return max(0.0, min(0.5, gap / 2.0))

    def _single_speaker_mapping(
        self, profile: SpeakerProfile, scores: dict[str, float]
    ) -> SpeakerRoleMapping:
        """One speaker means diarization found no second party; do not invent one.

        Leaving the role UNKNOWN is what makes transcript integrity validation fail the call, so a
        recording that was never separated into two parties is held rather than scored.
        """
        affinity = scores[profile.speaker_label]
        is_agent = affinity >= self.confidence_threshold
        logger.warning(
            "single_speaker_transcript",
            speaker=profile.speaker_label,
            agent_affinity=round(affinity, 2),
        )
        return SpeakerRoleMapping(
            mappings={
                profile.speaker_label: RoleAssignment(
                    business_role=SpeakerType.AGENT if is_agent else SpeakerType.UNKNOWN,
                    confidence=round(min(1.0, affinity), 2),
                    resolution_method="single_speaker",
                    reason_code="ONLY_ONE_SPEAKER_DETECTED",
                )
            },
            role_mapping_version=self.role_mapping_version,
        )
