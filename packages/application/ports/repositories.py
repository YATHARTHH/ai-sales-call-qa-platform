"""Application repository ports defining data persistence contracts."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from packages.domain.artifacts import Artifact
from packages.domain.audit import AuditEvent
from packages.domain.check_library import CheckDefinition, CheckVersion
from packages.domain.evaluation import (
    EvaluationResult,
    EvaluationRun,
    Evidence,
    GateDecision,
    HumanReview,
)
from packages.domain.jobs import PipelineJob
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
    async def get_recording_by_dialler_id(self, dialler_call_id: str) -> Recording | None:
        """Fetch recording metadata by dialler call identifier."""

    @abstractmethod
    async def save_recording_idempotent(self, recording: Recording) -> tuple[Recording, bool]:
        """Persist recording, handling dialler_call_id uniqueness conflicts atomically."""

    @abstractmethod
    async def save_transcript(
        self, transcript: Transcript, segments: list[TranscriptSegment]
    ) -> None:
        """Persist transcript metadata and utterance segments atomically."""

    async def save_transcript_idempotent(
        self, transcript: Transcript, segments: list[TranscriptSegment]
    ) -> tuple[Transcript, bool]:
        """Persist transcript, resolving transcription_key uniqueness conflicts idempotently."""
        raise NotImplementedError

    @abstractmethod
    async def get_transcript(self, transcript_id: str) -> Transcript | None:
        """Fetch transcript metadata by ID."""

    async def get_transcript_by_key(self, transcription_key: str) -> Transcript | None:
        """Fetch transcript by unique transcription idempotency key."""
        raise NotImplementedError

    async def get_transcript_by_recording_id(self, recording_id: str) -> Transcript | None:
        """Fetch transcript linked to a recording."""
        raise NotImplementedError

    @abstractmethod
    async def get_transcript_segments(self, transcript_id: str) -> list[TranscriptSegment]:
        """Fetch all ordered segments for a transcript."""

    async def get_segments_paginated(
        self,
        transcript_id: str,
        offset: int = 0,
        limit: int = 100,
        start_ms: int | None = None,
        end_ms: int | None = None,
        include_words: bool = False,
    ) -> tuple[list[TranscriptSegment], int]:
        """Fetch paginated segments with optional time-range scrubbing and word redaction."""
        raise NotImplementedError


class ArtifactRepositoryPort(ABC):
    """Repository interface for immutable content-hashed audio and derived artifacts."""

    @abstractmethod
    async def get_by_id(self, artifact_id: str) -> Artifact | None:
        """Fetch artifact by primary identifier."""

    @abstractmethod
    async def get_by_content_hash(self, content_hash: str) -> Artifact | None:
        """Fetch artifact by SHA-256 content hash."""

    @abstractmethod
    async def save_artifact_idempotent(self, artifact: Artifact) -> tuple[Artifact, bool]:
        """Persist artifact, returning existing one on content_hash uniqueness conflict."""


class JobRepositoryPort(ABC):
    """Repository interface for durable background pipeline jobs."""

    @abstractmethod
    async def get_by_id(self, job_id: str) -> PipelineJob | None:
        """Fetch job by ID."""

    @abstractmethod
    async def get_by_idempotency_key(self, idempotency_key: str) -> PipelineJob | None:
        """Fetch job by idempotency key."""

    @abstractmethod
    async def save_job_idempotent(self, job: PipelineJob) -> tuple[PipelineJob, bool]:
        """Persist pipeline job, returning existing one on idempotency_key uniqueness conflict."""

    async def claim_job_lease_atomic(
        self, job_id: str, worker_id: str, lease_duration_seconds: int = 60
    ) -> PipelineJob | None:
        """Atomically claim job lease and increment lease_generation in a single atomic SQL statement."""
        raise NotImplementedError

    async def complete_job_with_lease_fence(
        self,
        job_id: str,
        worker_id: str,
        lease_generation: int,
        completed_at: datetime | None = None,
    ) -> bool:
        """Atomically mark job COMPLETED only if the worker still owns the valid lease_generation."""
        raise NotImplementedError




class CheckLibraryRepositoryPort(ABC):
    """Repository interface for versioned compliance checklists."""

    @abstractmethod
    async def save_check_definition(self, check: CheckDefinition) -> None:
        """Persist check definition template."""

    @abstractmethod
    async def save_check_version(self, version: CheckVersion) -> None:
        """Persist a versioned check rule."""

    @abstractmethod
    async def get_check_versions(self, retailer_id: str, check_code: str) -> list[CheckVersion]:
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
    async def get_events_for_entity(self, entity_type: str, entity_id: str) -> list[AuditEvent]:
        """Retrieve historical audit events for a domain entity."""


class UnitOfWorkPort(ABC):
    """Atomic transactional boundary coordinating repositories."""

    sales: SaleRepositoryPort
    transcripts: TranscriptRepositoryPort
    artifacts: ArtifactRepositoryPort
    jobs: JobRepositoryPort
    audit: AuditRepositoryPort

    @abstractmethod
    async def commit(self) -> None:
        """Commit the active database transaction."""

    @abstractmethod
    async def rollback(self) -> None:
        """Rollback the active database transaction."""
