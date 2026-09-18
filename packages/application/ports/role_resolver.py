"""Speaker role resolution port for mapping diarization labels to business roles."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from packages.domain.transcript import SpeakerType


@dataclass(frozen=True)
class SpeakerProfile:
    """Aggregated speech profile for an anonymous speaker label (e.g. SPEAKER_00)."""

    speaker_label: str
    total_utterances: int
    first_spoken_ms: int
    total_speech_ms: int
    sample_text: str


@dataclass(frozen=True)
class RoleAssignment:
    """Resolved business role for a speaker with audit provenance."""

    business_role: SpeakerType
    confidence: float
    resolution_method: str
    reason_code: str


@dataclass(frozen=True)
class SpeakerRoleMapping:
    """Complete speaker-to-business-role mapping for a sales call."""

    mappings: dict[str, RoleAssignment]
    role_mapping_version: str

    def get_role(self, speaker_label: str) -> SpeakerType:
        if speaker_label in self.mappings:
            return self.mappings[speaker_label].business_role
        return SpeakerType.UNKNOWN


class SpeakerRoleResolverPort(ABC):
    """Port for inferring whether speakers are AGENT or CUSTOMER."""

    @abstractmethod
    def resolve(
        self, speakers: list[SpeakerProfile], context: dict[str, Any] | None = None
    ) -> SpeakerRoleMapping:
        """Assign business roles to speaker profiles with confidence scores."""
