"""Real-time event broadcaster port and Redis pub/sub implementation."""

from abc import ABC, abstractmethod
from typing import Any

from packages.contracts.events import RealtimeNotification
from packages.observability.logging import get_logger

logger = get_logger("events.broadcaster")


class EventBroadcasterPort(ABC):
    """Interface for broadcasting real-time notifications to auditor clients."""

    @abstractmethod
    async def broadcast_event(self, notification: RealtimeNotification) -> None:
        """Broadcast real-time notification to subscribers."""


class MockEventBroadcaster(EventBroadcasterPort):
    """In-memory mock broadcaster for tests and standalone mode."""

    def __init__(self):
        self.broadcasted_events: list[RealtimeNotification] = []

    async def broadcast_event(self, notification: RealtimeNotification) -> None:
        self.broadcasted_events.append(notification)
        logger.info(
            "mock_event_broadcasted",
            event_type=notification.event_type,
            tenant_id=notification.tenant_id,
            sale_id=notification.sale_id,
        )


class RedisEventBroadcaster(EventBroadcasterPort):
    """Redis Pub/Sub broadcaster distributing lightweight notifications to tenant channels."""

    def __init__(self, redis_client: Any):
        self._redis = redis_client

    async def broadcast_event(self, notification: RealtimeNotification) -> None:
        channel = f"tenant:{notification.tenant_id}:events"
        payload = notification.model_dump_json()
        try:
            await self._redis.publish(channel, payload)
            logger.info(
                "redis_event_published",
                channel=channel,
                event_type=notification.event_type,
                sale_id=notification.sale_id,
            )
        except Exception as exc:
            logger.warning("redis_publish_failed", error=str(exc), channel=channel)
