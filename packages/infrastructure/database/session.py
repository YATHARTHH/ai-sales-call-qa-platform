"""SQLAlchemy async engine and sessionmaker configuration."""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from packages.infrastructure.config.settings import settings

# Configure engine kwargs according to dialect
is_sqlite = settings.database_url.startswith("sqlite")
engine_kwargs: dict[str, Any] = {"echo": False, "future": True}
if not is_sqlite:
    engine_kwargs["pool_size"] = settings.database_pool_size
    engine_kwargs["max_overflow"] = settings.database_max_overflow

# Shared global async engine
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    **engine_kwargs,
)

# Shared async sessionmaker
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
