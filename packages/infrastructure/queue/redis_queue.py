"""Redis queue adapter implementing QueuePort."""

import json
from typing import Any

import redis.asyncio as aioredis

from packages.application.ports.queue import QueuePort
from packages.infrastructure.config.settings import settings


class RedisQueueAdapter(QueuePort):
    """Asynchronous job queue transport backed by Redis."""

    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or settings.redis_url

    async def _get_client(self) -> aioredis.Redis:
        return aioredis.from_url(self.redis_url, decode_responses=True)

    async def enqueue(self, job_name: str, payload: dict[str, Any]) -> str:
        """Push a job payload to a Redis list queue."""
        client = await self._get_client()
        try:
            serialized = json.dumps(payload)
            queue_key = f"queue:{job_name}"
            await client.rpush(queue_key, serialized)
            return payload.get("job_id", "queued")
        finally:
            await client.aclose()

    async def check_connection(self) -> bool:
        """Check if Redis responds to PING."""
        try:
            client = await self._get_client()
            try:
                return bool(await client.ping())
            finally:
                await client.aclose()
        except Exception:
            return False
