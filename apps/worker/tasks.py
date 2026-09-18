"""Background worker task execution functions."""

import asyncio
import os
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import select

from packages.application.ports.role_resolver import SpeakerProfile, SpeakerRoleResolverPort
from packages.application.ports.transcription import TranscriptionPort
from packages.application.services.audio_materializer import AudioMaterializer
from packages.application.services.canonical_serializer import CanonicalTranscriptSerializer
from packages.application.services.provider_validator import ProviderOutputValidator
from packages.domain.artifacts import Artifact
from packages.domain.audit import ActorType, AuditEvent
from packages.domain.exceptions import (
    LeaseLostError,
)
from packages.domain.jobs import FailureCategory, JobStatus, PipelineJob, RetryPolicy
from packages.domain.speech_metrics import SpeechBehaviorAnalyzer
from packages.domain.transcript import (
    SpeakerType,
    Transcript,
    TranscriptAvailability,
    TranscriptSegment,
)
from packages.infrastructure.config.settings import settings
from packages.infrastructure.database.models.jobs import PipelineJobModel
from packages.infrastructure.database.repositories.unit_of_work import SqlAlchemyUnitOfWork
from packages.infrastructure.database.session import async_session_factory
from packages.infrastructure.queue.redis_queue import RedisQueueAdapter
from packages.infrastructure.storage.minio_storage import MinioStorageAdapter
from packages.infrastructure.transcription.deterministic_adapter import (
    DeterministicTranscriptionAdapter,
)
from packages.infrastructure.transcription.role_resolver import (
    HeuristicSpeakerRoleResolver,
)
from packages.observability.logging import get_logger
from packages.observability.metrics import (
    WORKER_JOB_DURATION_SECONDS,
    WORKER_JOBS_TOTAL,
)

logger = get_logger("worker.tasks")


async def execute_smoke_job(
    job_id: str, worker_id: str, correlation_id: str, session_factory=None
) -> None:
    """Execute smoke test job verifying durable state persistence and metrics."""
    logger.info(
        "smoke_job_started", job_id=job_id, worker_id=worker_id, correlation_id=correlation_id
    )
    start_time = datetime.now(UTC)

    factory = session_factory or async_session_factory
    async with factory() as session:
        # 1. Fetch durable job from PostgreSQL
        stmt = select(PipelineJobModel).where(PipelineJobModel.id == job_id)
        result = await session.execute(stmt)
        job_model = result.scalar_one_or_none()

        if not job_model:
            logger.error("job_not_found_in_db", job_id=job_id)
            return

        # 2. Acquire worker lease
        job = PipelineJob(
            id=job_model.id,
            recording_id=job_model.recording_id,
            stage=job_model.stage,
            status=JobStatus(job_model.status),
            idempotency_key=job_model.idempotency_key,
            retry_count=job_model.retry_count,
            max_retries=job_model.max_retries,
        )
        job.acquire_lease(worker_id=worker_id)
        job_model.status = job.status.value
        job_model.worker_id = job.worker_id
        job_model.heartbeat_at = job.heartbeat_at
        job_model.lease_until = job.lease_until
        job_model.lease_generation = job.lease_generation
        job_model.started_at = job.started_at
        await session.commit()

        # 3. Simulate processing work
        await asyncio.sleep(0.5)

        # 4. Mark job completed
        job.mark_completed()
        job_model.status = job.status.value
        job_model.completed_at = job.completed_at
        job_model.lease_until = None
        await session.commit()

        duration = (datetime.now(UTC) - start_time).total_seconds()
        WORKER_JOBS_TOTAL.labels(stage=job.stage, status="COMPLETED").inc()
        WORKER_JOB_DURATION_SECONDS.labels(stage=job.stage).observe(duration)

        logger.info(
            "smoke_job_completed",
            job_id=job_id,
            duration_s=duration,
            status=job.status.value,
        )


async def execute_transcription_job(
    job_id: str,
    worker_id: str,
    correlation_id: str = "none",
    transcriber: TranscriptionPort | None = None,
    role_resolver: SpeakerRoleResolverPort | None = None,
    session_factory=None,
    storage_adapter=None,
    queue_adapter=None,
    eval_config_version: str = "eval-v1",
) -> None:
    """Execute durable transcription pipeline task with atomic lease fencing and idempotent evaluation dispatch."""
    start_time = datetime.now(UTC)
    logger.info(
        "transcription_job_started",
        job_id=job_id,
        worker_id=worker_id,
        correlation_id=correlation_id,
    )

    factory = session_factory or async_session_factory
    storage = storage_adapter or MinioStorageAdapter()
    queue = queue_adapter or RedisQueueAdapter()
    asr = transcriber or DeterministicTranscriptionAdapter()
    roles = role_resolver or HeuristicSpeakerRoleResolver()

    async with factory() as session:
        uow = SqlAlchemyUnitOfWork(session)

        # 1. Atomically claim job lease and increment lease_generation
        claimed_job = await uow.jobs.claim_job_lease_atomic(
            job_id=job_id,
            worker_id=worker_id,
            lease_duration_seconds=settings.worker_lease_duration_seconds,
        )
        if not claimed_job:
            logger.warning("transcription_job_not_claimable", job_id=job_id)
            return

        active_generation = claimed_job.lease_generation

        # 2. Fetch recording metadata
        recording = await uow.transcripts.get_recording(claimed_job.recording_id)
        if not recording:
            logger.error("recording_missing_for_job", recording_id=claimed_job.recording_id, job_id=job_id)
            return

        sale = await uow.sales.get_sale(recording.sale_id)
        lead_id = sale.lead_id if sale else "unknown-lead"
        audio_duration_ms = recording.validated_audio_duration_ms

        # 3. Replay Check: check if transcript already exists for this recording
        existing_tx = await uow.transcripts.get_transcript_by_recording_id(recording.id)
        if existing_tx and existing_tx.availability == TranscriptAvailability.AVAILABLE:
            logger.info("transcription_idempotent_replay_detected", transcript_id=existing_tx.id)
            eval_key = PipelineJob.build_evaluation_idempotency_key(
                recording.id, existing_tx.transcription_key, eval_config_version
            )
            existing_eval = await uow.jobs.get_by_idempotency_key(eval_key)
            if not existing_eval:
                eval_job = PipelineJob.create(
                    recording_id=recording.id,
                    stage="EVALUATING",
                    input_artifact_hash=existing_tx.output_artifact_id,
                    processor_version=eval_config_version,
                )
                eval_job.idempotency_key = eval_key
                await uow.jobs.save_job_idempotent(eval_job)
            else:
                eval_job = existing_eval

            # Lease fence on completion
            fenced = await uow.jobs.complete_job_with_lease_fence(
                job_id=job_id, worker_id=worker_id, lease_generation=active_generation
            )
            if not fenced:
                raise LeaseLostError(f"Worker '{worker_id}' lost lease on replay job '{job_id}'")

            await uow.commit()
            await queue.enqueue(
                "queue:evaluation",
                {"job_id": eval_job.id, "recording_id": recording.id, "correlation_id": correlation_id},
            )
            return

        # 4. Materialize audio with cryptographic verification
        audio_artifact = await uow.artifacts.get_by_id(recording.artifact_id)
        if not audio_artifact:
            logger.error("audio_artifact_missing", artifact_id=recording.artifact_id)
            return

        materializer = AudioMaterializer(
            storage=storage,
            bucket_name=settings.minio_bucket_recordings,
            max_file_size_bytes=settings.max_audio_upload_size_bytes,
        )
        audio_source = await materializer.materialize(audio_artifact)

        try:
            # 5. Execute ASR & diarization
            transcription_result = await asr.transcribe(audio_source)

            # 6. Validate untrusted provider output
            validator = ProviderOutputValidator()
            availability = validator.validate(transcription_result, audio_duration_ms)

            # 7. Role resolution
            profiles: list[SpeakerProfile] = []
            speaker_utterances: dict[str, list] = {}
            for u in transcription_result.utterances:
                speaker_utterances.setdefault(u.speaker_label, []).append(u)

            for label, utts in sorted(speaker_utterances.items()):
                first_spoken = min(u.start_ms for u in utts)
                total_speech = sum(u.end_ms - u.start_ms for u in utts)
                sample_text = " ".join(u.text for u in utts[:3])
                profiles.append(
                    SpeakerProfile(
                        speaker_label=label,
                        total_utterances=len(utts),
                        first_spoken_ms=first_spoken,
                        total_speech_ms=total_speech,
                        sample_text=sample_text,
                    )
                )

            role_mapping = roles.resolve(profiles)

            # 8. Speech behavior analysis
            analyzer = SpeechBehaviorAnalyzer()
            behavior = analyzer.analyze(
                utterances=transcription_result.utterances,
                audio_duration_ms=audio_duration_ms,
                role_mapping={k: v.business_role.value for k, v in role_mapping.mappings.items()},
            )

            # 9. Formulate provenance keys
            proc_version = Transcript.build_processor_version(
                transcription_result.asr_model,
                transcription_result.asr_model_version,
                transcription_result.diarization_provider,
                transcription_result.diarization_version,
            )
            t_key = Transcript.compute_transcription_key(
                source_audio_hash=audio_artifact.content_hash,
                processor_version=proc_version,
                transcription_config_hash=transcription_result.transcription_config_hash,
                diarization_config_hash=transcription_result.diarization_config_hash,
                role_mapping_version=role_mapping.role_mapping_version,
            )
            t_identity = Transcript.build_transcription_identity(
                source_audio_hash=audio_artifact.content_hash, processor_version=proc_version
            )

            # 10. Construct domain Transcript & TranscriptSegments
            transcript_id = f"tx-{claimed_job.recording_id}"
            out_artifact_key = f"transcripts/artifacts/{t_key[:16]}_{transcript_id}.json"

            segments: list[TranscriptSegment] = []
            sorted_utts = sorted(
                transcription_result.utterances, key=lambda u: (u.start_ms, u.end_ms, u.speaker_label)
            )
            for order, u in enumerate(sorted_utts, start=1):
                role_assigned = role_mapping.mappings.get(u.speaker_label)
                b_role = (
                    role_assigned.business_role
                    if role_assigned
                    else SpeakerType.UNKNOWN
                )
                r_conf = role_assigned.confidence if role_assigned else 1.0

                seg = TranscriptSegment.create(
                    transcript_id=transcript_id,
                    segment_order=order,
                    speaker_label=u.speaker_label,
                    business_role=b_role,
                    role_confidence=r_conf,
                    start_ms=u.start_ms,
                    end_ms=u.end_ms,
                    text=u.text,
                    words_json=[
                        {
                            "word": w.word,
                            "start_ms": w.start_ms,
                            "end_ms": w.end_ms,
                            "confidence": w.confidence,
                        }
                        for w in u.words
                    ],
                )
                segments.append(seg)

            transcript = Transcript(
                id=transcript_id,
                recording_id=recording.id,
                source_artifact_id=audio_artifact.id,
                output_artifact_id="",  # Will be set to out_artifact.id
                transcription_key=t_key,
                transcription_identity=t_identity,
                availability=availability,
                processor_version=proc_version,
                transcription_config_hash=transcription_result.transcription_config_hash,
                diarization_config_hash=transcription_result.diarization_config_hash,
                role_mapping_version=role_mapping.role_mapping_version,
                audio_duration_ms=audio_duration_ms,
                transcribed_coverage_end_ms=behavior.transcribed_coverage_end_ms,
                leading_uncovered_ms=behavior.leading_uncovered_ms,
                trailing_uncovered_ms=behavior.trailing_uncovered_ms,
                asr_provider=transcription_result.asr_provider,
                asr_model=transcription_result.asr_model,
                asr_model_version=transcription_result.asr_model_version,
                diarization_provider=transcription_result.diarization_provider,
                diarization_version=transcription_result.diarization_version,
                language=transcription_result.language,
                created_at=datetime.now(UTC),
            )

            # 11. Canonical JSON serialization & MinIO upload
            canonical_json_str = CanonicalTranscriptSerializer.serialize(
                transcript=transcript,
                result=transcription_result,
                role_map=role_mapping.mappings,
                behavior=behavior,
            )
            canonical_bytes = canonical_json_str.encode("utf-8")

            await storage.upload_object(
                bucket=settings.minio_bucket_artifacts,
                key=out_artifact_key,
                data=canonical_bytes,
                content_type="application/json",
            )

            # Create immutable derived artifact record
            out_artifact = Artifact.create(
                lead_id=lead_id,
                storage_key=out_artifact_key,
                raw_content=canonical_bytes,
                content_type="application/json",
            )
            await uow.artifacts.save_artifact_idempotent(out_artifact)

            # Update transcript output_artifact_id
            transcript = Transcript(
                id=transcript.id,
                recording_id=transcript.recording_id,
                source_artifact_id=transcript.source_artifact_id,
                output_artifact_id=out_artifact.id,
                transcription_key=transcript.transcription_key,
                transcription_identity=transcript.transcription_identity,
                availability=transcript.availability,
                processor_version=transcript.processor_version,
                transcription_config_hash=transcript.transcription_config_hash,
                diarization_config_hash=transcript.diarization_config_hash,
                role_mapping_version=transcript.role_mapping_version,
                audio_duration_ms=transcript.audio_duration_ms,
                transcribed_coverage_end_ms=transcript.transcribed_coverage_end_ms,
                leading_uncovered_ms=transcript.leading_uncovered_ms,
                trailing_uncovered_ms=transcript.trailing_uncovered_ms,
                asr_provider=transcript.asr_provider,
                asr_model=transcript.asr_model,
                asr_model_version=transcript.asr_model_version,
                diarization_provider=transcript.diarization_provider,
                diarization_version=transcript.diarization_version,
                language=transcript.language,
                created_at=transcript.created_at,
            )

            # 12. Persist transcript & segments
            behavior_dict = asdict(behavior)
            await uow.transcripts.save_transcript_idempotent(
                transcript=transcript,
                segments=segments,
                behavior_json=behavior_dict,
            )

            # 13. Create downstream evaluation job with stable lineage
            eval_key = PipelineJob.build_evaluation_idempotency_key(
                recording.id, t_key, eval_config_version
            )
            eval_job = PipelineJob.create(
                recording_id=recording.id,
                stage="EVALUATING",
                input_artifact_hash=out_artifact.content_hash,
                processor_version=eval_config_version,
            )
            eval_job.idempotency_key = eval_key
            saved_eval_job, _ = await uow.jobs.save_job_idempotent(eval_job)

            # 14. Append audit event
            audit_event = AuditEvent.record(
                entity_type="TRANSCRIPT",
                entity_id=transcript.id,
                action="GENERATED",
                actor_type=ActorType.WORKER,
                actor_id=worker_id,
                correlation_id=correlation_id,
                payload_json={
                    "transcription_key": t_key,
                    "availability": availability.value,
                    "processor_version": proc_version,
                    "audio_duration_ms": audio_duration_ms,
                    "talk_time_ms": behavior.total_speech_ms,
                },
            )
            await uow.audit.record_event(audit_event)

            # 15. Enforce Atomic Lease Fencing on Completion
            fenced = await uow.jobs.complete_job_with_lease_fence(
                job_id=job_id,
                worker_id=worker_id,
                lease_generation=active_generation,
            )
            if not fenced:
                raise LeaseLostError(
                    f"Worker '{worker_id}' lost lease on job '{job_id}' (generation {active_generation}); transaction aborted."
                )

            # 16. Commit single transactional boundary
            await uow.commit()

            # 17. Dispatch downstream Redis message strictly AFTER DB commit
            await queue.enqueue(
                "queue:evaluation",
                {"job_id": saved_eval_job.id, "recording_id": recording.id, "correlation_id": correlation_id},
            )

            duration = (datetime.now(UTC) - start_time).total_seconds()
            WORKER_JOBS_TOTAL.labels(stage="TRANSCRIBING", status="COMPLETED").inc()
            WORKER_JOB_DURATION_SECONDS.labels(stage="TRANSCRIBING").observe(duration)

            logger.info(
                "transcription_job_completed",
                job_id=job_id,
                transcript_id=transcript.id,
                availability=availability.value,
                duration_s=duration,
            )

        except LeaseLostError as exc:
            await uow.rollback()
            logger.warning("transcription_lease_lost_rollback", error=str(exc))
            raise
        except Exception as exc:
            await uow.rollback()
            logger.error("transcription_job_failed", error=str(exc), exc_info=True)
            raise
        finally:
            # 18. Cleanup bounded temporary audio file in finally block
            if audio_source and os.path.exists(audio_source.local_path):
                try:
                    os.remove(audio_source.local_path)
                except OSError:
                    pass


async def recover_stale_jobs(policy: RetryPolicy | None = None, session_factory=None) -> int:
    """Identify and reclaim jobs left in RUNNING whose lease has expired."""
    active_policy = policy or RetryPolicy()
    recovered_count = 0
    now = datetime.now(UTC)

    factory = session_factory or async_session_factory
    async with factory() as session:
        stmt = select(PipelineJobModel).where(
            PipelineJobModel.status == JobStatus.RUNNING.value,
            PipelineJobModel.lease_until < now,
        )
        result = await session.execute(stmt)
        stale_jobs = result.scalars().all()

        for job_model in stale_jobs:
            logger.warning(
                "stale_job_detected",
                job_id=job_model.id,
                lease_until=job_model.lease_until.isoformat() if job_model.lease_until else None,
                worker_id=job_model.worker_id,
            )

            if active_policy.should_retry(FailureCategory.TRANSIENT, job_model.retry_count):
                job_model.retry_count += 1
                job_model.status = JobStatus.QUEUED.value
                job_model.last_error = "Worker lease expired; job reclaimed by recovery routine."
                logger.info(
                    "stale_job_requeued", job_id=job_model.id, retry_count=job_model.retry_count
                )
            else:
                job_model.status = JobStatus.DEAD_LETTER.value
                job_model.last_error = "Worker lease expired and max retries exceeded."
                logger.error("stale_job_dead_lettered", job_id=job_model.id)

            job_model.lease_until = None
            recovered_count += 1

        if recovered_count > 0:
            await session.commit()

    return recovered_count
