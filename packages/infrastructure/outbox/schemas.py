"""Outbox schemas, delivery enums, and status contracts."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OutboxStatus(str, Enum):
    """Transactional outbox lifecycle states."""

    PENDING = "PENDING"
    DELIVERING = "DELIVERING"
    PUBLISHED = "PUBLISHED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    DEAD_LETTER = "DEAD_LETTER"


class OutboxEventClaim(BaseModel):
    """Claimed outbox event ready for dispatch."""

    model_config = ConfigDict(frozen=True)

    id: str
    tenant_id: str
    event_type: str
    event_schema_version: str
    aggregate_type: str
    aggregate_id: str
    idempotency_key: str
    payload_json: dict[str, Any]
    attempt_count: int
    created_at: datetime


class DeliveryResult(BaseModel):
    """Result of attempting to publish an outbox event downstream."""

    model_config = ConfigDict(frozen=True)

    success: bool
    status_code: int | None = None
    error_message: str | None = None
    is_retryable: bool = False
    is_already_processed: bool = False
