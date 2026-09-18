"""Append-only audit event logging domain models."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ActorType(StrEnum):
    HUMAN = "HUMAN"
    SYSTEM = "SYSTEM"
    WORKER = "WORKER"
    AI = "AI"


@dataclass(frozen=True)
class AuditEvent:
    """Immutable, append-only record of domain mutations and compliance overrides.

    Invariants:
    - INSERT only; UPDATE and DELETE operations are strictly prohibited.
    - Captures actor identity and correlation ID for end-to-end tracing.
    """

    id: str
    entity_type: str
    entity_id: str
    action: str
    actor_type: ActorType
    actor_id: str
    correlation_id: str
    payload_json: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def record(
        cls,
        entity_type: str,
        entity_id: str,
        action: str,
        actor_type: ActorType,
        actor_id: str,
        correlation_id: str,
        payload_json: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> "AuditEvent":
        return cls(
            id=event_id or str(uuid.uuid4()),
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_type=actor_type,
            actor_id=actor_id,
            correlation_id=correlation_id,
            payload_json=payload_json or {},
            created_at=datetime.now(UTC),
        )
