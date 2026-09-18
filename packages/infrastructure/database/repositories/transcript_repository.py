"""SQLAlchemy implementation of TranscriptRepositoryPort."""

import asyncio

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from packages.application.ports.repositories import TranscriptRepositoryPort
from packages.domain.transcript import (
    Recording,
    SpeakerType,
    Transcript,
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
        return Recording(
            id=model.id,
            sale_id=model.sale_id,
            artifact_id=model.artifact_id,
            dialler_call_id=model.dialler_call_id,
            duration_seconds=model.duration_seconds,
            call_date=model.call_date,
            created_at=model.created_at,
        )

    async def get_recording_by_dialler_id(self, dialler_call_id: str) -> Recording | None:
        stmt = select(RecordingModel).where(RecordingModel.dialler_call_id == dialler_call_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            return None
        return Recording(
            id=model.id,
            sale_id=model.sale_id,
            artifact_id=model.artifact_id,
            dialler_call_id=model.dialler_call_id,
            duration_seconds=model.duration_seconds,
            call_date=model.call_date,
            created_at=model.created_at,
        )

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

    async def save_transcript(
        self, transcript: Transcript, segments: list[TranscriptSegment]
    ) -> None:
        t_model = TranscriptModel(
            id=transcript.id,
            recording_id=transcript.recording_id,
            source_artifact_id=transcript.source_artifact_id,
            output_artifact_id=transcript.output_artifact_id,
            asr_provider=transcript.asr_provider,
            asr_model=transcript.asr_model,
            asr_model_version=transcript.asr_model_version,
            diarization_provider=transcript.diarization_provider,
            diarization_version=transcript.diarization_version,
            language=transcript.language,
            created_at=transcript.created_at,
        )
        await self._session.merge(t_model)

        for seg in segments:
            seg_model = TranscriptSegmentModel(
                id=seg.id,
                transcript_id=seg.transcript_id,
                segment_order=seg.segment_order,
                speaker=seg.speaker.value,
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
                text=seg.text,
                words_json=seg.words_json,
            )
            await self._session.merge(seg_model)

        await self._session.flush()

    async def get_transcript(self, transcript_id: str) -> Transcript | None:
        stmt = select(TranscriptModel).where(TranscriptModel.id == transcript_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            return None
        return Transcript(
            id=model.id,
            recording_id=model.recording_id,
            source_artifact_id=model.source_artifact_id,
            output_artifact_id=model.output_artifact_id,
            asr_provider=model.asr_provider,
            asr_model=model.asr_model,
            asr_model_version=model.asr_model_version,
            diarization_provider=model.diarization_provider,
            diarization_version=model.diarization_version,
            language=model.language,
            created_at=model.created_at,
        )

    async def get_transcript_segments(self, transcript_id: str) -> list[TranscriptSegment]:
        stmt = (
            select(TranscriptSegmentModel)
            .where(TranscriptSegmentModel.transcript_id == transcript_id)
            .order_by(TranscriptSegmentModel.segment_order.asc())
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [
            TranscriptSegment(
                id=r.id,
                transcript_id=r.transcript_id,
                segment_order=r.segment_order,
                speaker=SpeakerType(r.speaker),
                start_ms=r.start_ms,
                end_ms=r.end_ms,
                text=r.text,
                words_json=r.words_json,
            )
            for r in rows
        ]
