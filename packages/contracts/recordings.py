"""API contracts and schemas for audio recording ingestion and retrieval."""

from datetime import datetime

from pydantic import BaseModel, Field


class RecordingIngestRequest(BaseModel):
    """Request schema for pre-staged S3 recording ingestion."""

    sale_id: str = Field(..., description="Associated commercial sale ID")
    dialler_call_id: str = Field(..., description="Unique dialler telephony call identifier")
    call_date: datetime = Field(..., description="Timestamp when call took place")
    storage_key: str = Field(..., description="Pre-staged storage key in recordings bucket")
    duration_seconds: float | None = Field(None, ge=0.0, description="Optional reported duration")


class RecordingResponse(BaseModel):
    """Response schema representing an ingested audio recording."""

    id: str
    sale_id: str
    artifact_id: str
    dialler_call_id: str
    duration_seconds: float
    call_date: datetime
    content_hash: str
    created_at: datetime


class RecordingUploadResponse(BaseModel):
    """Response schema returned following recording upload or ingestion."""

    recording_id: str
    artifact_id: str
    sale_id: str
    dialler_call_id: str
    content_hash: str
    duration_seconds: float
    is_duplicate: bool
    job_id: str | None = None
