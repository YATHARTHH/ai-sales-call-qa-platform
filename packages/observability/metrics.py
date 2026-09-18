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

# Recording Ingestion Metrics (Low-Cardinality)
RECORDING_INGESTION_TOTAL = Counter(
    "recording_ingestion_total",
    "Total recording ingestion events handled",
    ["status"],  # success, duplicate_call, duplicate_content, failure
)

RECORDING_INGESTION_DURATION_SECONDS = Histogram(
    "recording_ingestion_duration_seconds",
    "Time taken to ingest and store audio recordings in seconds",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

RECORDING_AUDIO_DURATION_SECONDS = Histogram(
    "recording_audio_duration_seconds",
    "Call audio duration distribution in seconds",
    buckets=(30.0, 60.0, 180.0, 300.0, 600.0, 900.0, 1200.0, 1800.0, 2400.0),
)

RECORDING_FILE_SIZE_BYTES = Histogram(
    "recording_file_size_bytes",
    "Size of ingested audio files in bytes",
    buckets=(100_000, 500_000, 1_000_000, 5_000_000, 20_000_000, 50_000_000, 100_000_000),
)

__all__ = [
    "API_REQUESTS_TOTAL",
    "API_REQUEST_DURATION_SECONDS",
    "WORKER_JOBS_TOTAL",
    "WORKER_JOB_DURATION_SECONDS",
    "WORKER_JOB_FAILURES_TOTAL",
    "RECORDING_INGESTION_TOTAL",
    "RECORDING_INGESTION_DURATION_SECONDS",
    "RECORDING_AUDIO_DURATION_SECONDS",
    "RECORDING_FILE_SIZE_BYTES",
    "generate_latest",
]
