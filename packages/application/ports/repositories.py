"""Application repository ports defining data persistence contracts."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from packages.domain.audit import AuditEvent
from packages.domain.check_library import CheckDefinition, CheckVersion
from packages.domain.evaluation import (
    EvaluationResult,
    EvaluationRun,
    Evidence,
    GateDecision,
    HumanReview,
)
from packages.domain.retail import Agent, Campaign, Lead, Retailer, Sale
from packages.domain.transcript import Recording, Transcript, TranscriptSegment


class SaleRepositoryPort(ABC):
    """Repository interface for retail sales, leads, campaigns, and agents."""

    @abstractmethod
    async def save_retailer(self, retailer: Retailer) -> None:
        """Persist a retailer entity."""

    @abstractmethod
    async def get_retailer(self, retailer_id: str) -> Retailer | None:
        """Fetch retailer by ID."""

    @abstractmethod
    async def save_campaign(self, campaign: Campaign) -> None:
        """Persist a campaign entity."""

    @abstractmethod
    async def save_agent(self, agent: Agent) -> None:
        """Persist an agent entity."""

    @abstractmethod
    async def save_lead(self, lead: Lead) -> None:
        """Persist customer lead information."""

    @abstractmethod
    async def get_lead(self, lead_id: str) -> Lead | None:
        """Fetch lead by ID."""

    @abstractmethod
    async def save_sale(self, sale: Sale) -> None:
        """Persist commercial sale record."""

    @abstractmethod
    async def get_sale(self, sale_id: str) -> Sale | None:
        """Fetch sale record by ID."""


class TranscriptRepositoryPort(ABC):
    """Repository interface for audio recordings and timestamped transcripts."""

    @abstractmethod
    async def save_recording(self, recording: Recording) -> None:
        """Persist recording metadata linked to audio artifact."""

    @abstractmethod
    async def get_recording(self, recording_id: str) -> Recording | None:
        """Fetch recording metadata."""

    @abstractmethod
    async def save_transcript(
        self, transcript: Transcript, segments: list[TranscriptSegment]
    ) -> None:
        """Persist transcript metadata and utterance segments atomically."""

    @abstractmethod
    async def get_transcript(self, transcript_id: str) -> Transcript | None:
        """Fetch transcript metadata by ID."""

    @abstractmethod
    async def get_transcript_segments(
        self, transcript_id: str
    ) -> list[TranscriptSegment]:
        """Fetch all ordered segments for a transcript."""


class CheckLibraryRepositoryPort(ABC):
    """Repository interface for versioned compliance checklists."""

    @abstractmethod
    async def save_check_definition(self, check: CheckDefinition) -> None:
        """Persist check definition template."""

    @abstractmethod
    async def save_check_version(self, version: CheckVersion) -> None:
        """Persist a versioned check rule."""

    @abstractmethod
    async def get_check_versions(
        self, retailer_id: str, check_code: str
    ) -> list[CheckVersion]:
        """Fetch all historical versions of a check for a retailer."""

    @abstractmethod
    async def get_retailer_checklist(
        self, retailer_id: str, call_date: datetime
    ) -> list[CheckVersion]:
        """Resolve all active check versions for a retailer on a specific call date."""


class EvaluationRepositoryPort(ABC):
    """Repository interface for evaluation runs, results, evidence, and gate decisions."""

    @abstractmethod
    async def save_evaluation_run(
        self,
        run: EvaluationRun,
        results: list[EvaluationResult],
        evidence_items: list[Evidence],
    ) -> None:
        """Persist an entire evaluation run atomically."""

    @abstractmethod
    async def save_gate_decision(self, decision: GateDecision) -> None:
        """Persist deterministic gate decision."""

    @abstractmethod
    async def save_human_review(self, review: HumanReview) -> None:
        """Persist human review / TL override."""

    @abstractmethod
    async def get_evaluation_lineage(self, sale_id: str) -> dict[str, Any] | None:
        """Fetch the full unbroken evaluation and review lineage for a sale."""


class AuditRepositoryPort(ABC):
    """Repository interface for append-only audit events."""

    @abstractmethod
    async def record_event(self, event: AuditEvent) -> None:
        """Append an audit event (INSERT only)."""

    @abstractmethod
    async def get_events_for_entity(
        self, entity_type: str, entity_id: str
    ) -> list[AuditEvent]:
        """Retrieve historical audit events for a domain entity."""
