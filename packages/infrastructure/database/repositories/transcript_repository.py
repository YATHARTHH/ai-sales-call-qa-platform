"""SQLAlchemy implementation of TranscriptRepositoryPort."""

import asyncio
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from packages.application.ports.repositories import TranscriptRepositoryPort
from packages.domain.transcript import (
    Recording,
    SpeakerType,
    Transcript,
    TranscriptAvailability,
    TranscriptSegment,
)
from packages.infrastructure.database.models.transcripts import (
    RecordingModel,
    TranscriptModel,
    TranscriptSegmentModel,
)


class SqlAlchemyTranscriptRepository(TranscriptRepositoryPort):
    """Persistence adapter for audio recordings, transcripts, and speaker segments."""

    def __init__(self, session: AsyncSession):
        self._session = session

    def _to_recording_domain(self, model: RecordingModel) -> Recording:
        return Recording(
            id=model.id,
            sale_id=model.sale_id,
            artifact_id=model.artifact_id,
            dialler_call_id=model.dialler_call_id,
            duration_seconds=model.duration_seconds,
            call_date=model.call_date,
            created_at=model.created_at,
        )

    def _to_transcript_domain(self, model: TranscriptModel) -> Transcript:
        return Transcript(
            id=model.id,
            recording_id=model.recording_id,
            source_artifact_id=model.source_artifact_id,
            output_artifact_id=model.output_artifact_id,
            transcription_key=model.transcription_key,
            transcription_identity=model.transcription_identity,
            availability=TranscriptAvailability(model.availability),
            processor_version=model.processor_version,
            transcription_config_hash=model.transcription_config_hash,
            diarization_config_hash=model.diarization_config_hash,
            role_mapping_version=model.role_mapping_version,
            audio_duration_ms=model.audio_duration_ms,
            transcribed_coverage_end_ms=model.transcribed_coverage_end_ms,
            leading_uncovered_ms=model.leading_uncovered_ms,
            trailing_uncovered_ms=model.trailing_uncovered_ms,
            asr_provider=model.asr_provider,
            asr_model=model.asr_model,
            asr_model_version=model.asr_model_version,
            diarization_provider=model.diarization_provider,
            diarization_version=model.diarization_version,
            language=model.language,
            created_at=model.created_at,
        )

    def _to_segment_domain(
        self, model: TranscriptSegmentModel, include_words: bool = True
    ) -> TranscriptSegment:
        return TranscriptSegment(
            id=model.id,
            transcript_id=model.transcript_id,
            segment_order=model.segment_order,
            speaker_label=model.speaker_label,
            business_role=SpeakerType(model.business_role),
            role_confidence=model.role_confidence,
            start_ms=model.start_ms,
            end_ms=model.end_ms,
            text=model.text,
            words_json=model.words_json if include_words else [],
        )

    async def save_recording(self, recording: Recording) -> None:
        model = RecordingModel(
            id=recording.id,
            sale_id=recording.sale_id,
            artifact_id=recording.artifact_id,
            dialler_call_id=recording.dialler_call_id,
            duration_seconds=recording.duration_seconds,
            call_date=recording.call_date,
            created_at=recording.created_at,
        )
        await self._session.merge(model)
        await self._session.flush()

    async def get_recording(self, recording_id: str) -> Recording | None:
        stmt = select(RecordingModel).where(RecordingModel.id == recording_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_recording_domain(model)

    async def get_recording_by_dialler_id(self, dialler_call_id: str) -> Recording | None:
        stmt = select(RecordingModel).where(RecordingModel.dialler_call_id == dialler_call_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_recording_domain(model)

    async def save_recording_idempotent(self, recording: Recording) -> tuple[Recording, bool]:
        existing = await self.get_recording_by_dialler_id(recording.dialler_call_id)
        if existing:
            return existing, False

        model = RecordingModel(
            id=recording.id,
            sale_id=recording.sale_id,
            artifact_id=recording.artifact_id,
            dialler_call_id=recording.dialler_call_id,
            duration_seconds=recording.duration_seconds,
            call_date=recording.call_date,
            created_at=recording.created_at,
        )

        is_inserted = False
        async with self._session.begin_nested():
            try:
                self._session.add(model)
                await self._session.flush()
                is_inserted = True
            except IntegrityError:
                pass

        if is_inserted:
            return recording, True

        winner = await self.get_recording_by_dialler_id(recording.dialler_call_id)
        if winner is None:
            for _ in range(30):
                await asyncio.sleep(0.05)
                winner = await self.get_recording_by_dialler_id(recording.dialler_call_id)
                if winner is not None:
                    break
        if winner is not None:
            return winner, False
        raise RuntimeError("Failed to resolve recording on dialler_call_id conflict")

    def _build_transcript_model(
        self, transcript: Transcript, behavior_json: dict[str, Any] | None = None
    ) -> TranscriptModel:
        # Fallback defaults for keys if not provided (for older tests)
        t_key = (
            transcript.transcription_key
            or f"key-{transcript.id}-{transcript.recording_id}"
        )
        t_identity = (
            transcript.transcription_identity
            or f"identity-{transcript.id}"
        )
        p_version = transcript.processor_version or "default-v1"
        t_conf_hash = transcript.transcription_config_hash or "default-hash"
        d_conf_hash = transcript.diarization_config_hash or "default-hash"
        r_version = transcript.role_mapping_version or "default-role-v1"

        return TranscriptModel(
            id=transcript.id,
            recording_id=transcript.recording_id,
            source_artifact_id=transcript.source_artifact_id,
            output_artifact_id=transcript.output_artifact_id,
            transcription_key=t_key,
            transcription_identity=t_identity,
            availability=transcript.availability.value,
            processor_version=p_version,
            transcription_config_hash=t_conf_hash,
            diarization_config_hash=d_conf_hash,
            role_mapping_version=r_version,
            audio_duration_ms=transcript.audio_duration_ms,
            transcribed_coverage_end_ms=transcript.transcribed_coverage_end_ms,
            leading_uncovered_ms=transcript.leading_uncovered_ms,
            trailing_uncovered_ms=transcript.trailing_uncovered_ms,
            behavior_json=behavior_json,
            asr_provider=transcript.asr_provider,
            asr_model=transcript.asr_model,
            asr_model_version=transcript.asr_model_version,
            diarization_provider=transcript.diarization_provider,
            diarization_version=transcript.diarization_version,
            language=transcript.language,
            created_at=transcript.created_at,
        )

    async def save_transcript(
        self,
        transcript: Transcript,
        segments: list[TranscriptSegment],
        behavior_json: dict[str, Any] | None = None,
    ) -> None:
        t_model = self._build_transcript_model(transcript, behavior_json)
        await self._session.merge(t_model)

        for seg in segments:
            seg_model = TranscriptSegmentModel(
                id=seg.id,
                transcript_id=seg.transcript_id,
                segment_order=seg.segment_order,
                speaker_label=seg.speaker_label,
                business_role=seg.business_role.value,
                role_confidence=seg.role_confidence,
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
                text=seg.text,
                words_json=seg.words_json,
            )
            await self._session.merge(seg_model)

        await self._session.flush()

    async def save_transcript_idempotent(
        self,
        transcript: Transcript,
        segments: list[TranscriptSegment],
        behavior_json: dict[str, Any] | None = None,
    ) -> tuple[Transcript, bool]:
        """Save transcript, returning existing entity if transcription_key conflict occurs."""
        if transcript.transcription_key:
            existing = await self.get_transcript_by_key(transcript.transcription_key)
            if existing:
                return existing, False

        t_model = self._build_transcript_model(transcript, behavior_json)

        is_inserted = False
        async with self._session.begin_nested():
            try:
                self._session.add(t_model)
                for seg in segments:
                    seg_model = TranscriptSegmentModel(
                        id=seg.id,
                        transcript_id=seg.transcript_id,
                        segment_order=seg.segment_order,
                        speaker_label=seg.speaker_label,
                        business_role=seg.business_role.value,
                        role_confidence=seg.role_confidence,
                        start_ms=seg.start_ms,
                        end_ms=seg.end_ms,
                        text=seg.text,
                        words_json=seg.words_json,
                    )
                    self._session.add(seg_model)
                await self._session.flush()
                is_inserted = True
            except IntegrityError:
                pass

        if is_inserted:
            return transcript, True

        winner = await self.get_transcript_by_key(transcript.transcription_key)
        if winner is not None:
            return winner, False
        return transcript, False

    async def get_transcript(self, transcript_id: str) -> Transcript | None:
        stmt = select(TranscriptModel).where(TranscriptModel.id == transcript_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_transcript_domain(model)

    async def get_transcript_by_key(self, transcription_key: str) -> Transcript | None:
        stmt = select(TranscriptModel).where(TranscriptModel.transcription_key == transcription_key)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_transcript_domain(model)

    async def get_transcript_by_recording_id(self, recording_id: str) -> Transcript | None:
        stmt = select(TranscriptModel).where(TranscriptModel.recording_id == recording_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_transcript_domain(model)

    async def get_transcript_segments(self, transcript_id: str) -> list[TranscriptSegment]:
        stmt = (
            select(TranscriptSegmentModel)
            .where(TranscriptSegmentModel.transcript_id == transcript_id)
            .order_by(TranscriptSegmentModel.segment_order.asc())
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [self._to_segment_domain(r, include_words=True) for r in rows]

    async def get_segments_paginated(
        self,
        transcript_id: str,
        offset: int = 0,
        limit: int = 100,
        start_ms: int | None = None,
        end_ms: int | None = None,
        include_words: bool = False,
    ) -> tuple[list[TranscriptSegment], int]:
        # Count query
        count_stmt = select(func.count(TranscriptSegmentModel.id)).where(
            TranscriptSegmentModel.transcript_id == transcript_id
        )
        if start_ms is not None:
            count_stmt = count_stmt.where(TranscriptSegmentModel.end_ms >= start_ms)
        if end_ms is not None:
            count_stmt = count_stmt.where(TranscriptSegmentModel.start_ms <= end_ms)

        total_res = await self._session.execute(count_stmt)
        total = total_res.scalar() or 0

        # Items query
        stmt = (
            select(TranscriptSegmentModel)
            .where(TranscriptSegmentModel.transcript_id == transcript_id)
        )
        if start_ms is not None:
            stmt = stmt.where(TranscriptSegmentModel.end_ms >= start_ms)
        if end_ms is not None:
            stmt = stmt.where(TranscriptSegmentModel.start_ms <= end_ms)

        stmt = (
            stmt.order_by(TranscriptSegmentModel.segment_order.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        items = [self._to_segment_domain(r, include_words=include_words) for r in rows]
        return items, total
