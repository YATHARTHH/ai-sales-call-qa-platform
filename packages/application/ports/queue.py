"""Queue port contract for asynchronous background job dispatch."""

from abc import ABC, abstractmethod
from typing import Any


class QueuePort(ABC):
    """Abstract interface for queue dispatch (Redis/ARQ)."""

    @abstractmethod
    async def enqueue(
        self, job_name: str, payload: dict[str, Any]
    ) -> str:
        """Enqueue a background task returning the message ID."""

    @abstractmethod
    async def check_connection(self) -> bool:
        """Verify message broker connectivity."""
