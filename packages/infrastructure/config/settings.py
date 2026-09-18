"""Centralized, strictly-typed configuration settings using Pydantic Settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Platform configuration loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="SalesCall QA", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_secret_key: str = Field(
        default="dev-insecure-secret-key-change-in-production",
        alias="APP_SECRET_KEY",
    )
    cors_allowed_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        alias="CORS_ALLOWED_ORIGINS",
    )

    # PostgreSQL Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/salescall_qa",
        alias="DATABASE_URL",
    )
    database_pool_size: int = Field(default=10, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=20, alias="DATABASE_MAX_OVERFLOW")

    # Redis Queue & Cache
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL",
    )

    # MinIO Object Storage
    minio_endpoint: str = Field(default="localhost:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="minioadmin", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="minioadmin", alias="MINIO_SECRET_KEY")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")
    minio_bucket_recordings: str = Field(
        default="sales-call-recordings", alias="MINIO_BUCKET_RECORDINGS"
    )
    minio_bucket_artifacts: str = Field(
        default="sales-call-artifacts", alias="MINIO_BUCKET_ARTIFACTS"
    )
    minio_public_endpoint: str = Field(default="localhost:9000", alias="MINIO_PUBLIC_ENDPOINT")
    max_audio_upload_size_bytes: int = Field(
        default=524_288_000, alias="MAX_AUDIO_UPLOAD_SIZE_BYTES"
    )
    webhook_secret: str = Field(default="dev-dialler-webhook-secret", alias="WEBHOOK_SECRET")

    # Background Workers & Leases
    worker_concurrency: int = Field(default=4, alias="WORKER_CONCURRENCY")
    worker_heartbeat_interval_seconds: int = Field(
        default=15, alias="WORKER_HEARTBEAT_INTERVAL_SECONDS"
    )
    worker_lease_duration_seconds: int = Field(default=60, alias="WORKER_LEASE_DURATION_SECONDS")
    max_job_retries: int = Field(default=3, alias="MAX_JOB_RETRIES")

    # Observability
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")
    prometheus_metrics_enabled: bool = Field(default=True, alias="PROMETHEUS_METRICS_ENABLED")

    @property
    def cors_origins_list(self) -> list[str]:
        """Convert comma-separated CORS origins into a typed list."""
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


# Global singleton settings instance
settings = Settings()
