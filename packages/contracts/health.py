"""Health and readiness contract schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness probe response (verifies the HTTP server is alive)."""

    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    """Readiness probe response (verifies database, cache, and storage connectivity)."""

    status: Literal["ready", "not_ready"]
    dependencies: dict[str, str] = Field(
        ...,
        description="Health status of external dependencies (postgres, redis, minio)",
    )
