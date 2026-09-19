"""Integration tests for OutboxRepository atomic claiming and OutboxDispatcher lifecycle."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from packages.infrastructure.crm.publisher import MockCrmPublisher
from packages.infrastructure.database.base import Base
from packages.infrastructure.database.models.evaluations import OutboxEventModel
from packages.infrastructure.database.repositories.outbox_repository import (
    SqlAlchemyOutboxRepository,
)
from packages.infrastructure.events.redis_publisher import MockEventBroadcaster
from packages.infrastructure.outbox.dispatcher import OutboxDispatcher
from packages.infrastructure.outbox.schemas import OutboxStatus


@pytest.fixture
async def outbox_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_outbox_claim_and_publish_success(outbox_session_factory):
    crm_publisher = MockCrmPublisher()
    broadcaster = MockEventBroadcaster()
    dispatcher = OutboxDispatcher(
        session_factory=outbox_session_factory,
        crm_publisher=crm_publisher,
        event_broadcaster=broadcaster,
    )

    # 1. Enqueue event in outbox
    async with outbox_session_factory() as session:
        repo = SqlAlchemyOutboxRepository(session)
        await repo.save_event(
            event_type="GateDecisionChanged",
            aggregate_type="SALE",
            aggregate_id="sale_101",
            payload={"sale_id": "sale_101", "gate_status": "HELD"},
            tenant_id="retailer-01",
            idempotency_key="idemp_101",
        )
        await session.commit()

    # 2. Dispatch batch
    processed_count = await dispatcher.process_batch(batch_size=10)
    assert processed_count == 1

    # 3. Assert downstream delivery
    assert len(crm_publisher.published_events) == 1
    assert crm_publisher.published_events[0].idempotency_key == "idemp_101"
    assert len(broadcaster.broadcasted_events) == 1
    assert broadcaster.broadcasted_events[0].event_type == "GateDecisionChanged"

    # 4. Assert DB state is PUBLISHED
    async with outbox_session_factory() as session:
        res = await session.execute(select(OutboxEventModel).where(OutboxEventModel.idempotency_key == "idemp_101"))
        model = res.scalar_one()
        assert model.status == OutboxStatus.PUBLISHED.value
        assert model.published_at is not None
        assert model.attempt_count == 1


@pytest.mark.asyncio
async def test_outbox_retry_scheduled_on_transient_failure(outbox_session_factory):
    crm_publisher = MockCrmPublisher(should_fail=True, is_retryable=True, error_message="HTTP 503 Service Unavailable")
    dispatcher = OutboxDispatcher(
        session_factory=outbox_session_factory,
        crm_publisher=crm_publisher,
        base_backoff_seconds=2.0,
    )

    async with outbox_session_factory() as session:
        repo = SqlAlchemyOutboxRepository(session)
        await repo.save_event(
            event_type="SaleSubmitted",
            aggregate_type="SALE",
            aggregate_id="sale_202",
            payload={"sale_id": "sale_202"},
            tenant_id="retailer-01",
            idempotency_key="idemp_202",
        )
        await session.commit()

    processed_count = await dispatcher.process_batch(batch_size=10)
    assert processed_count == 1

    async with outbox_session_factory() as session:
        res = await session.execute(select(OutboxEventModel).where(OutboxEventModel.idempotency_key == "idemp_202"))
        model = res.scalar_one()
        assert model.status == OutboxStatus.RETRY_SCHEDULED.value
        assert model.attempt_count == 1
        assert "503" in model.last_error
        assert model.next_attempt_at is not None
        next_dt = model.next_attempt_at.replace(tzinfo=UTC) if model.next_attempt_at.tzinfo is None else model.next_attempt_at
        assert next_dt > datetime.now(UTC)


@pytest.mark.asyncio
async def test_outbox_dead_letter_on_fatal_failure(outbox_session_factory):
    crm_publisher = MockCrmPublisher(should_fail=True, is_retryable=False, error_message="HTTP 400 Bad Request")
    dispatcher = OutboxDispatcher(
        session_factory=outbox_session_factory,
        crm_publisher=crm_publisher,
    )

    async with outbox_session_factory() as session:
        repo = SqlAlchemyOutboxRepository(session)
        await repo.save_event(
            event_type="CancellationRequested",
            aggregate_type="SALE",
            aggregate_id="sale_303",
            payload={"sale_id": "sale_303"},
            tenant_id="retailer-01",
            idempotency_key="idemp_303",
        )
        await session.commit()

    processed_count = await dispatcher.process_batch(batch_size=10)
    assert processed_count == 1

    async with outbox_session_factory() as session:
        res = await session.execute(select(OutboxEventModel).where(OutboxEventModel.idempotency_key == "idemp_303"))
        model = res.scalar_one()
        assert model.status == OutboxStatus.DEAD_LETTER.value
        assert "400" in model.last_error


@pytest.mark.asyncio
async def test_outbox_idempotent_on_409_conflict(outbox_session_factory):
    crm_publisher = MockCrmPublisher(simulate_conflict=True)
    dispatcher = OutboxDispatcher(
        session_factory=outbox_session_factory,
        crm_publisher=crm_publisher,
    )

    async with outbox_session_factory() as session:
        repo = SqlAlchemyOutboxRepository(session)
        await repo.save_event(
            event_type="SaleSubmitted",
            aggregate_type="SALE",
            aggregate_id="sale_404",
            payload={"sale_id": "sale_404"},
            tenant_id="retailer-01",
            idempotency_key="idemp_404",
        )
        await session.commit()

    processed_count = await dispatcher.process_batch(batch_size=10)
    assert processed_count == 1

    async with outbox_session_factory() as session:
        res = await session.execute(select(OutboxEventModel).where(OutboxEventModel.idempotency_key == "idemp_404"))
        model = res.scalar_one()
        # 409 conflict is treated as already processed -> PUBLISHED
        assert model.status == OutboxStatus.PUBLISHED.value
        assert model.published_at is not None
