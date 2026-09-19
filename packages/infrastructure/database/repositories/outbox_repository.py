"""SQLAlchemy implementation of OutboxRepositoryPort."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.application.ports.repositories import OutboxRepositoryPort
from packages.infrastructure.database.models.evaluations import OutboxEventModel
from packages.infrastructure.outbox.schemas import OutboxEventClaim, OutboxStatus


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
            status=OutboxStatus.PENDING.value,
            created_at=datetime.now(UTC),
        )
        self._session.add(model)
        await self._session.flush()

    async def claim_pending_events(
        self, batch_size: int = 10, lease_seconds: int = 60
    ) -> list[OutboxEventClaim]:
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=lease_seconds)

        stmt = (
            select(OutboxEventModel)
            .where(
                OutboxEventModel.status.in_([OutboxStatus.PENDING.value, OutboxStatus.RETRY_SCHEDULED.value]),
                or_(OutboxEventModel.locked_until.is_(None), OutboxEventModel.locked_until < now),
                or_(OutboxEventModel.next_attempt_at.is_(None), OutboxEventModel.next_attempt_at <= now),
            )
            .order_by(OutboxEventModel.created_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        res = await self._session.execute(stmt)
        events = res.scalars().all()
        claims = []
        for ev in events:
            ev.status = OutboxStatus.DELIVERING.value
            ev.locked_until = lease_until
            ev.attempt_count += 1
            claims.append(
                OutboxEventClaim(
                    id=ev.id,
                    tenant_id=ev.tenant_id,
                    event_type=ev.event_type,
                    event_schema_version=ev.event_schema_version,
                    aggregate_type=ev.aggregate_type,
                    aggregate_id=ev.aggregate_id,
                    idempotency_key=ev.idempotency_key,
                    payload_json=ev.payload_json,
                    attempt_count=ev.attempt_count,
                    created_at=ev.created_at,
                )
            )
        await self._session.flush()
        return claims

    async def mark_published(self, event_id: str) -> None:
        stmt = select(OutboxEventModel).where(OutboxEventModel.id == event_id)
        res = await self._session.execute(stmt)
        ev = res.scalar_one_or_none()
        if ev:
            ev.status = OutboxStatus.PUBLISHED.value
            ev.published_at = datetime.now(UTC)
            ev.locked_until = None
            await self._session.flush()

    async def mark_retry(
        self, event_id: str, error_message: str, next_attempt_at: datetime
    ) -> None:
        stmt = select(OutboxEventModel).where(OutboxEventModel.id == event_id)
        res = await self._session.execute(stmt)
        ev = res.scalar_one_or_none()
        if ev:
            ev.status = OutboxStatus.RETRY_SCHEDULED.value
            ev.last_error = error_message
            ev.next_attempt_at = next_attempt_at
            ev.locked_until = None
            await self._session.flush()

    async def mark_dead_letter(self, event_id: str, error_message: str) -> None:
        stmt = select(OutboxEventModel).where(OutboxEventModel.id == event_id)
        res = await self._session.execute(stmt)
        ev = res.scalar_one_or_none()
        if ev:
            ev.status = OutboxStatus.DEAD_LETTER.value
            ev.last_error = error_message
            ev.locked_until = None
            await self._session.flush()
