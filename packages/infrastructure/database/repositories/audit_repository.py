"""SQLAlchemy implementation of AuditRepositoryPort."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.application.ports.repositories import AuditRepositoryPort
from packages.domain.audit import ActorType, AuditEvent
from packages.infrastructure.database.models.evaluations import AuditEventModel


class SqlAlchemyAuditRepository(AuditRepositoryPort):
    """Append-only audit trail repository adapter.

    Enforces immutable write-once behavior for compliance and legal defensibility.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def record_event(self, event: AuditEvent) -> None:
        model = AuditEventModel(
            id=event.id,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            action=event.action,
            actor_type=event.actor_type.value,
            actor_id=event.actor_id,
            correlation_id=event.correlation_id,
            payload_json=event.payload_json,
            created_at=event.created_at,
        )
        self._session.add(model)
        await self._session.flush()

    async def get_events_for_entity(
        self, entity_type: str, entity_id: str
    ) -> list[AuditEvent]:
        stmt = (
            select(AuditEventModel)
            .where(
                AuditEventModel.entity_type == entity_type,
                AuditEventModel.entity_id == entity_id,
            )
            .order_by(AuditEventModel.created_at.asc())
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [
            AuditEvent(
                id=r.id,
                entity_type=r.entity_type,
                entity_id=r.entity_id,
                action=r.action,
                actor_type=ActorType(r.actor_type),
                actor_id=r.actor_id,
                correlation_id=r.correlation_id,
                payload_json=r.payload_json,
                created_at=r.created_at,
            )
            for r in rows
        ]
