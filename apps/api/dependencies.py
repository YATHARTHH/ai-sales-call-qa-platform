"""Dependency injection providers for FastAPI routers."""

from packages.application.ports.queue import QueuePort
from packages.application.ports.storage import StoragePort
from packages.infrastructure.queue.redis_queue import RedisQueueAdapter
from packages.infrastructure.storage.minio_storage import MinioStorageAdapter


async def get_storage() -> StoragePort:
    """Provide MinIO storage adapter."""
    return MinioStorageAdapter()


async def get_queue() -> QueuePort:
    """Provide Redis queue adapter."""
    return RedisQueueAdapter()
