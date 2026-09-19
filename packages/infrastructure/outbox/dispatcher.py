"""Outbox dispatcher daemon claiming events atomically and publishing downstream."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from packages.contracts.events import RealtimeNotification
from packages.infrastructure.crm.publisher import CrmPublisherPort
from packages.infrastructure.database.repositories.outbox_repository import (
    SqlAlchemyOutboxRepository,
)
from packages.infrastructure.events.redis_publisher import EventBroadcasterPort
from packages.infrastructure.outbox.schemas import OutboxEventClaim
from packages.observability.logging import get_logger

logger = get_logger("outbox.dispatcher")


class OutboxDispatcher:
    """Dispatches claimed outbox events to downstream CRM/webhooks and broadcasts notifications."""

    def __init__(
        self,
        session_factory: Any,
        crm_publisher: CrmPublisherPort,
        event_broadcaster: EventBroadcasterPort | None = None,
        max_attempts: int = 5,
        base_backoff_seconds: float = 2.0,
        max_backoff_seconds: float = 300.0,
    ):
        self._session_factory = session_factory
        self._crm_publisher = crm_publisher
        self._event_broadcaster = event_broadcaster
        self.max_attempts = max_attempts
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds

    async def claim_batch(
        self, batch_size: int = 10, lease_seconds: int = 60
    ) -> list[OutboxEventClaim]:
        """Claims a batch of pending events in an isolated database transaction."""
        async with self._session_factory() as session:
            repo = SqlAlchemyOutboxRepository(session)
            claims = await repo.claim_pending_events(
                batch_size=batch_size, lease_seconds=lease_seconds
            )
            await session.commit()
            return claims

    async def process_batch(
        self, batch_size: int = 10, lease_seconds: int = 60
    ) -> int:
        """Claims pending events and delivers them downstream, committing status for each."""
        claims = await self.claim_batch(batch_size=batch_size, lease_seconds=lease_seconds)
        if not claims:
            return 0

        for claim in claims:
            await self._dispatch_single_claim(claim)

        return len(claims)

    async def _dispatch_single_claim(self, claim: OutboxEventClaim) -> None:
        """Delivers event externally and records outcome in a separate database transaction."""
        logger.info(
            "dispatching_outbox_event",
            event_id=claim.id,
            event_type=claim.event_type,
            tenant_id=claim.tenant_id,
            attempt=claim.attempt_count,
        )

        delivery_result = await self._crm_publisher.publish_event(claim)

        async with self._session_factory() as session:
            repo = SqlAlchemyOutboxRepository(session)

            if delivery_result.success:
                await repo.mark_published(claim.id)
                await session.commit()

                logger.info(
                    "outbox_event_published_successfully",
                    event_id=claim.id,
                    event_type=claim.event_type,
                    is_conflict_idempotent=delivery_result.is_already_processed,
                )

                # Broadcast real-time notification after successful DB commit
                if self._event_broadcaster:
                    notification = RealtimeNotification(
                        event_id=claim.id,
                        event_type=claim.event_type,
                        tenant_id=claim.tenant_id,
                        sale_id=str(claim.payload_json.get("sale_id", claim.aggregate_id)),
                        evaluation_run_id=claim.payload_json.get("evaluation_run_id"),
                        occurred_at=datetime.now(UTC).isoformat(),
                    )
                    await self._event_broadcaster.broadcast_event(notification)

            else:
                # Handle failure: determine if dead-letter or retry
                error_msg = delivery_result.error_message or "Unknown delivery error"
                if (not delivery_result.is_retryable) or (claim.attempt_count >= self.max_attempts):
                    await repo.mark_dead_letter(claim.id, error_msg)
                    logger.error(
                        "outbox_event_dead_lettered",
                        event_id=claim.id,
                        event_type=claim.event_type,
                        attempts=claim.attempt_count,
                        error=error_msg,
                    )
                else:
                    backoff = min(
                        self.max_backoff_seconds,
                        self.base_backoff_seconds * (2 ** (claim.attempt_count - 1)),
                    )
                    next_attempt = datetime.now(UTC) + timedelta(seconds=backoff)
                    await repo.mark_retry(claim.id, error_msg, next_attempt)
                    logger.warning(
                        "outbox_event_retry_scheduled",
                        event_id=claim.id,
                        event_type=claim.event_type,
                        attempts=claim.attempt_count,
                        next_attempt_at=next_attempt.isoformat(),
                        error=error_msg,
                    )

                await session.commit()

    async def run_loop(
        self, poll_interval_seconds: float = 2.0, stop_event: asyncio.Event | None = None
    ) -> None:
        """Continuous polling worker loop."""
        logger.info("outbox_dispatcher_loop_started", interval=poll_interval_seconds)
        while True:
            if stop_event and stop_event.is_set():
                logger.info("outbox_dispatcher_loop_stopped")
                break

            try:
                processed = await self.process_batch()
                if processed == 0:
                    await asyncio.sleep(poll_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("outbox_dispatcher_loop_error", error=str(exc), exc_info=True)
                await asyncio.sleep(poll_interval_seconds)
