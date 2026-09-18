"""Prometheus metrics collectors for API and async workers with safe fallback."""

try:
    from prometheus_client import Counter, Histogram, generate_latest
except ImportError:
    class _DummyMetric:
        """Graceful fallback when prometheus_client is not installed."""

        def __init__(self, *args, **kwargs) -> None:
            pass

        def inc(self, *args, **kwargs) -> None:
            pass

        def observe(self, *args, **kwargs) -> None:
            pass

        def labels(self, *args, **kwargs) -> "_DummyMetric":
            return self

    Counter = _DummyMetric  # type: ignore[misc]
    Histogram = _DummyMetric  # type: ignore[misc]

    def generate_latest() -> bytes:  # type: ignore[misc]
        return b"# prometheus_client not installed in local environment\n"

# API HTTP Metrics
API_REQUESTS_TOTAL = Counter(
    "api_requests_total",
    "Total count of HTTP requests handled by the API",
    ["method", "endpoint", "status_code"],
)

API_REQUEST_DURATION_SECONDS = Histogram(
    "api_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Background Worker Metrics
WORKER_JOBS_TOTAL = Counter(
    "worker_jobs_total",
    "Total background pipeline jobs processed",
    ["stage", "status"],
)

WORKER_JOB_DURATION_SECONDS = Histogram(
    "worker_job_duration_seconds",
    "Time taken to execute pipeline jobs in seconds",
    ["stage"],
    buckets=(0.1, 0.5, 1.0, 5.0, 15.0, 30.0, 60.0, 120.0),
)

WORKER_JOB_FAILURES_TOTAL = Counter(
    "worker_job_failures_total",
    "Total background pipeline job failures",
    ["stage", "failure_category"],
)

__all__ = [
    "API_REQUESTS_TOTAL",
    "API_REQUEST_DURATION_SECONDS",
    "WORKER_JOBS_TOTAL",
    "WORKER_JOB_DURATION_SECONDS",
    "WORKER_JOB_FAILURES_TOTAL",
    "generate_latest",
]
