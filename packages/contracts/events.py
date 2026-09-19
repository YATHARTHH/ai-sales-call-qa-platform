"""Standard event envelope and real-time event notification schemas."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventEnvelope(BaseModel):
    """Standard event envelope contract for outbox, CRM webhooks, and audit logs."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    event_type: str
    event_schema_version: str = "1.0"
    tenant_id: str
    aggregate_type: str
    aggregate_id: str
    occurred_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    idempotency_key: str
    data: dict[str, Any] = Field(default_factory=dict)


class RealtimeNotification(BaseModel):
    """Lightweight real-time notification payload broadcasted via Redis and SSE."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    event_type: str
    tenant_id: str
    sale_id: str
    evaluation_run_id: str | None = None
    occurred_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    version: int = 1
