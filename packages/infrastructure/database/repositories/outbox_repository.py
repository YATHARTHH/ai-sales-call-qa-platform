"""SQLAlchemy implementation of OutboxRepositoryPort."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from packages.application.ports.repositories import OutboxRepositoryPort
from packages.infrastructure.database.models.evaluations import OutboxEventModel


class SqlAlchemyOutboxRepository(OutboxRepositoryPort):
    """Transactional outbox repository ensuring exactly-once asynchronous event publishing."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save_event(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
        tenant_id: str,
        idempotency_key: str,
    ) -> None:
        model = OutboxEventModel(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            event_schema_version="v1",
            idempotency_key=idempotency_key,
            payload_json=payload,
            created_at=datetime.now(UTC),
        )
        self._session.add(model)
        await self._session.flush()
