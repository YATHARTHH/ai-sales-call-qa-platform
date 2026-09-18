"""Pytest fixtures and environment configuration for tests."""

import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set testing environment variables before importing application
os.environ["APP_ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

import packages.infrastructure.database.models  # noqa: F401
from packages.infrastructure.database.base import Base


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def test_db_session():
    """Provide an in-memory SQLite session for fast isolated unit/integration tests."""
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        yield session

    await test_engine.dispose()


@pytest.fixture
async def pg_db_session():
    """Authoritative integration fixture for PostgreSQL when available."""
    pg_url = os.getenv("PG_TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/salescall_qa")
    try:
        engine = create_async_engine(pg_url, echo=False)
        async with engine.connect() as conn:
            await conn.run_sync(lambda _: None)
    except Exception as exc:
        pytest.skip(f"Authoritative PostgreSQL not reachable at {pg_url}: {exc}")

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        yield session

    await engine.dispose()
