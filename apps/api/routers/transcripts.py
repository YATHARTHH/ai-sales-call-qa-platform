"""FastAPI router for transcripts, paginated segments, and speech behavior."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import (
    get_current_principal,
    verify_recording_access,
    verify_transcript_access,
)
from packages.contracts.security import Principal
from packages.contracts.transcripts import (
    PaginatedSegmentsResponse,
    SpeechBehaviorResponse,
    TranscriptResponse,
    TranscriptSegmentResponse,
    WordTimingSchema,
)
from packages.domain.security.pci_redaction import redact_pci_text
from packages.domain.jobs import JobStatus
from packages.infrastructure.database.models.jobs import PipelineJobModel
from packages.infrastructure.database.models.sales import SaleModel
from packages.infrastructure.database.models.transcripts import RecordingModel, TranscriptModel
from packages.infrastructure.database.repositories.transcript_repository import (
    SqlAlchemyTranscriptRepository,
)
from packages.infrastructure.database.session import get_db_session
from packages.observability.logging import get_logger

logger = get_logger("api.transcripts")

router = APIRouter(tags=["transcripts"])


@router.get(
    "/transcripts/{transcript_id}",
    response_model=TranscriptResponse,
    summary="Get transcript metadata and provenance identity",
)
async def get_transcript_metadata(
    access: Annotated[
        tuple[TranscriptModel, RecordingModel, SaleModel],
        Depends(verify_transcript_access),
    ],
    principal: Principal = Depends(get_current_principal),
) -> TranscriptResponse:
    """Retrieve transcript metadata with tenant access verification."""
    transcript, _, _ = access
    logger.info(
        "transcript_metadata_accessed",
        transcript_id=transcript.id,
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
    )
    return TranscriptResponse(
        id=transcript.id,
        recording_id=transcript.recording_id,
        source_artifact_id=transcript.source_artifact_id,
        output_artifact_id=transcript.output_artifact_id,
        transcription_key=transcript.transcription_key,
        transcription_identity=transcript.transcription_identity,
        availability=transcript.availability,
        processor_version=transcript.processor_version,
        asr_provider=transcript.asr_provider,
        asr_model=transcript.asr_model,
        asr_model_version=transcript.asr_model_version,
        diarization_provider=transcript.diarization_provider,
        diarization_version=transcript.diarization_version,
        language=transcript.language,
        created_at=transcript.created_at,
    )


@router.get(
    "/transcripts/{transcript_id}/segments",
    response_model=PaginatedSegmentsResponse,
    summary="Get paginated timestamped utterance segments",
)
async def get_transcript_segments(
    access: Annotated[
        tuple[TranscriptModel, RecordingModel, SaleModel],
        Depends(verify_transcript_access),
    ],
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(100, ge=1, le=500, description="Page size limit (max 500)"),
    start_ms: int | None = Query(None, ge=0, description="Filter segments starting after start_ms"),
    end_ms: int | None = Query(None, ge=0, description="Filter segments ending before end_ms"),
    include_words: bool = Query(
        False, description="Include word-level timestamps (heavy payload)"
    ),
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> PaginatedSegmentsResponse:
    """Retrieve paginated utterance segments with optional word timings and time scrubbing."""
    transcript, _, _ = access
    repo = SqlAlchemyTranscriptRepository(session)
    segments, total = await repo.get_segments_paginated(
        transcript_id=transcript.id,
        offset=offset,
        limit=limit,
        start_ms=start_ms,
        end_ms=end_ms,
        include_words=include_words,
    )

    items = [
        TranscriptSegmentResponse(
            id=seg.id,
            segment_order=seg.segment_order,
            speaker_label=seg.speaker_label,
            business_role=seg.business_role.value,
            role_confidence=seg.role_confidence,
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            text=redact_pci_text(seg.text),
            words=[
                WordTimingSchema(
                    word=w["word"],
                    start_ms=w["start_ms"],
                    end_ms=w["end_ms"],
                    confidence=w.get("confidence"),
                )
                for w in seg.words_json
            ]
            if include_words
            else None,
        )
        for seg in segments
    ]

    logger.info(
        "transcript_segments_accessed",
        transcript_id=transcript.id,
        offset=offset,
        limit=limit,
        include_words=include_words,
        user_id=principal.user_id,
    )

    return PaginatedSegmentsResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/transcripts/{transcript_id}/behavior",
    response_model=SpeechBehaviorResponse,
    summary="Get speech behavior and dead-air analysis metrics",
)
async def get_speech_behavior_metrics(
    access: Annotated[
        tuple[TranscriptModel, RecordingModel, SaleModel],
        Depends(verify_transcript_access),
    ],
    principal: Principal = Depends(get_current_principal),
) -> SpeechBehaviorResponse:
    """Retrieve objective speech behavior metrics (talk percentages, dead air, interruptions)."""
    transcript, _, _ = access

    behavior = transcript.behavior_json or {}
    return SpeechBehaviorResponse(
        audio_duration_ms=transcript.audio_duration_ms,
        transcribed_coverage_end_ms=transcript.transcribed_coverage_end_ms,
        leading_uncovered_ms=transcript.leading_uncovered_ms,
        trailing_uncovered_ms=transcript.trailing_uncovered_ms,
        has_uncovered_audio=behavior.get("has_uncovered_audio", False),
        agent_talk_ms=behavior.get("agent_talk_ms", 0),
        customer_talk_ms=behavior.get("customer_talk_ms", 0),
        total_speech_ms=behavior.get("total_speech_ms", 0),
        agent_talk_percentage=behavior.get("agent_talk_percentage", 0.0),
        customer_talk_percentage=behavior.get("customer_talk_percentage", 0.0),
        conversational_occupancy_percentage=behavior.get(
            "conversational_occupancy_percentage", 0.0
        ),
        agent_words_per_minute=behavior.get("agent_words_per_minute", 0.0),
        customer_words_per_minute=behavior.get("customer_words_per_minute", 0.0),
        dead_air_gaps=behavior.get("dead_air_gaps", []),
        interruption_candidates=behavior.get("interruption_candidates", []),
    )


@router.get(
    "/recordings/{recording_id}/transcript",
    response_model=TranscriptResponse,
    summary="Get transcript associated with a recording",
)
async def get_recording_transcript(
    access: Annotated[tuple[RecordingModel, SaleModel], Depends(verify_recording_access)],
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> TranscriptResponse:
    """Retrieve transcript linked to recording. Returns 409 if transcription is still running."""
    recording, _ = access
    repo = SqlAlchemyTranscriptRepository(session)
    transcript = await repo.get_transcript_by_recording_id(recording.id)

    if not transcript:
        # Check if pipeline job is actively transcribing
        job_stmt = (
            select(PipelineJobModel)
            .where(
                PipelineJobModel.recording_id == recording.id,
                PipelineJobModel.stage == "TRANSCRIBING",
            )
            .order_by(PipelineJobModel.created_at.desc())
        )
        job_res = await session.execute(job_stmt)
        job = job_res.scalar_one_or_none()

        if job and job.status in {JobStatus.RUNNING.value, JobStatus.QUEUED.value}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Transcription is currently in progress for this recording.",
            )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No transcript found for recording: {recording.id}",
        )

    return TranscriptResponse(
        id=transcript.id,
        recording_id=transcript.recording_id,
        source_artifact_id=transcript.source_artifact_id,
        output_artifact_id=transcript.output_artifact_id,
        transcription_key=transcript.transcription_key,
        transcription_identity=transcript.transcription_identity,
        availability=transcript.availability.value,
        processor_version=transcript.processor_version,
        asr_provider=transcript.asr_provider,
        asr_model=transcript.asr_model,
        asr_model_version=transcript.asr_model_version,
        diarization_provider=transcript.diarization_provider,
        diarization_version=transcript.diarization_version,
        language=transcript.language,
        created_at=transcript.created_at,
    )
