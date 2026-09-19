"""CRM and Webhook event publisher implementations."""

import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import httpx

from packages.contracts.events import EventEnvelope
from packages.infrastructure.crm.signing import compute_webhook_signature
from packages.infrastructure.outbox.schemas import DeliveryResult, OutboxEventClaim
from packages.observability.logging import get_logger

logger = get_logger("crm.publisher")


class CrmPublisherPort(ABC):
    """Interface for publishing claimed outbox events to downstream CRM or webhooks."""

    @abstractmethod
    async def publish_event(self, claim: OutboxEventClaim) -> DeliveryResult:
        """Deliver an outbox event claim."""


class MockCrmPublisher(CrmPublisherPort):
    """In-memory mock publisher for unit tests and local zero-dependency development."""

    def __init__(
        self,
        should_fail: bool = False,
        is_retryable: bool = True,
        simulate_conflict: bool = False,
        error_message: str = "Mock CRM connection error",
    ):
        self.published_events: list[OutboxEventClaim] = []
        self.should_fail = should_fail
        self.is_retryable = is_retryable
        self.simulate_conflict = simulate_conflict
        self.error_message = error_message

    async def publish_event(self, claim: OutboxEventClaim) -> DeliveryResult:
        if self.simulate_conflict:
            return DeliveryResult(
                success=True,
                status_code=409,
                is_already_processed=True,
                error_message="Resource already committed downstream",
            )

        if self.should_fail:
            return DeliveryResult(
                success=False,
                status_code=503 if self.is_retryable else 400,
                is_retryable=self.is_retryable,
                error_message=self.error_message,
            )

        self.published_events.append(claim)
        logger.info(
            "mock_crm_event_delivered",
            event_id=claim.id,
            event_type=claim.event_type,
            aggregate_id=claim.aggregate_id,
        )
        return DeliveryResult(success=True, status_code=200)


class WebhookEventPublisher(CrmPublisherPort):
    """HTTP webhook publisher delivering signed JSON payloads with idempotent delivery."""

    def __init__(
        self,
        endpoint_url: str,
        secret_key: str,
        key_id: str = "qa-platform-v1",
        timeout_seconds: float = 15.0,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.endpoint_url = endpoint_url
        self.secret_key = secret_key
        self.key_id = key_id
        self.timeout_seconds = timeout_seconds
        self._client = http_client

    async def publish_event(self, claim: OutboxEventClaim) -> DeliveryResult:
        envelope = EventEnvelope(
            event_id=claim.id,
            event_type=claim.event_type,
            event_schema_version=claim.event_schema_version,
            tenant_id=claim.tenant_id,
            aggregate_type=claim.aggregate_type,
            aggregate_id=claim.aggregate_id,
            occurred_at=datetime.now(UTC).isoformat(),
            idempotency_key=claim.idempotency_key,
            data=claim.payload_json,
        )
        raw_body = json.dumps(envelope.model_dump(), sort_keys=True, separators=(",", ":"))
        timestamp = str(int(datetime.now(UTC).timestamp()))
        signature = compute_webhook_signature(timestamp, raw_body, self.secret_key)

        headers = {
            "Content-Type": "application/json",
            "X-QA-Key-Id": self.key_id,
            "X-QA-Timestamp": timestamp,
            "X-QA-Signature": signature,
            "X-Idempotency-Key": claim.idempotency_key,
        }

        try:
            client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
            try:
                response = await client.post(self.endpoint_url, content=raw_body, headers=headers)
            finally:
                if self._client is None:
                    await client.aclose()

            if 200 <= response.status_code < 300:
                return DeliveryResult(success=True, status_code=response.status_code)

            if response.status_code == 409:
                return DeliveryResult(
                    success=True,
                    status_code=409,
                    is_already_processed=True,
                    error_message=response.text,
                )

            # Permanent fatal client errors
            if response.status_code in (400, 422, 401, 403):
                return DeliveryResult(
                    success=False,
                    status_code=response.status_code,
                    is_retryable=False,
                    error_message=f"HTTP {response.status_code}: {response.text[:200]}",
                )

            # Retryable server or rate limit errors
            return DeliveryResult(
                success=False,
                status_code=response.status_code,
                is_retryable=True,
                error_message=f"HTTP {response.status_code}: {response.text[:200]}",
            )

        except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as exc:
            return DeliveryResult(
                success=False,
                status_code=None,
                is_retryable=True,
                error_message=f"Transport error: {str(exc)}",
            )
        except Exception as exc:
            return DeliveryResult(
                success=False,
                status_code=None,
                is_retryable=False,
                error_message=f"Unexpected delivery exception: {str(exc)}",
            )
