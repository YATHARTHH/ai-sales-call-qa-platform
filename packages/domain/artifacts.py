"""Immutable source and derived artifact definitions."""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class Artifact:
    """Immutable representation of a source recording or derived data payload.

    Invariants:
    - Immutable once created (frozen dataclass).
    - Content hash is guaranteed to match the SHA-256 of the raw data.
    - Stable UUID identifier.
    """

    id: str
    lead_id: str
    storage_key: str
    content_hash: str
    content_type: str
    size_bytes: int
    created_at: datetime
    duration_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        lead_id: str,
        storage_key: str,
        raw_content: bytes,
        content_type: str,
        duration_seconds: float | None = None,
        metadata: dict[str, Any] | None = None,
        artifact_id: str | None = None,
    ) -> "Artifact":
        """Factory method computing SHA-256 content hash atomically."""
        content_hash = cls.calculate_hash(raw_content)
        return cls(
            id=artifact_id or str(uuid.uuid4()),
            lead_id=lead_id,
            storage_key=storage_key,
            content_hash=content_hash,
            content_type=content_type,
            size_bytes=len(raw_content),
            duration_seconds=duration_seconds,
            created_at=datetime.now(UTC),
            metadata=dict(metadata or {}),
        )

    @staticmethod
    def calculate_hash(content: bytes) -> str:
        """Calculate standard SHA-256 hex digest of raw binary bytes."""
        return hashlib.sha256(content).hexdigest()
