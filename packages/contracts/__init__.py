"""SalesCall QA API and Event Contracts."""

from packages.contracts.errors import ErrorDetail, ErrorResponse
from packages.contracts.health import HealthResponse, ReadinessResponse

__all__ = [
    "ErrorDetail",
    "ErrorResponse",
    "HealthResponse",
    "ReadinessResponse",
]
