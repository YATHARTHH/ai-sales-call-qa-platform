"""SalesCall QA Observability Layer (Structured logging, metrics, tracing)."""

from packages.observability.logging import configure_logging, get_logger
from packages.observability.metrics import (
    API_REQUEST_DURATION_SECONDS,
    API_REQUESTS_TOTAL,
    WORKER_JOB_DURATION_SECONDS,
    WORKER_JOB_FAILURES_TOTAL,
    WORKER_JOBS_TOTAL,
)

__all__ = [
    "configure_logging",
    "get_logger",
    "API_REQUESTS_TOTAL",
    "API_REQUEST_DURATION_SECONDS",
    "WORKER_JOBS_TOTAL",
    "WORKER_JOB_DURATION_SECONDS",
    "WORKER_JOB_FAILURES_TOTAL",
]
