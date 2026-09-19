"""End-to-end pipeline test: a real WAV file in, a gate decision and a CRM event out.

Every other test exercises one stage. This one runs the whole chain on genuine 16-bit PCM audio
against the full 30-check retailer checklist, so the wiring that a demo depends on — artifact
hashing, audio materialisation, diarization, role resolution, evaluation, the policy gate, and the
transactional outbox message the CRM consumes — is proven to hold together.

The audio is channel-accurate but wordless (see ``packages/infrastructure/audio/synthetic.py``), so
transcription replays a fixture built from the same turn list. That keeps audio and transcript in
agreement while leaving ASR accuracy to be measured separately against a real recording.
"""

import hashlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

from apps.worker.tasks import execute_evaluation_job, execute_transcription_job
from packages.application.ports.queue import QueuePort
from packages.application.ports.storage import StoragePort
from packages.domain.jobs import JobStatus
from packages.domain.retail import Agent, Campaign, Lead, Retailer, Sale
from packages.domain.state import GateStatus
from packages.domain.transcript import Recording
from packages.evaluation.accuracy import harness as gold
from packages.evaluation.checklists.builder import build_check_library
from packages.evaluation.checklists.energy_retailer_v1 import ENERGY_RETAILER_CHECKLIST_V1
from packages.infrastructure.audio.synthetic import AudioTurn, synthesize_stereo_wav
from packages.infrastructure.audio.wav_inspector import WavAudioInspector
from packages.infrastructure.database.models.artifacts import ArtifactModel
from packages.infrastructure.database.models.evaluations import (
    GateDecisionModel,
    OutboxEventModel,
)
from packages.infrastructure.database.models.jobs import PipelineJobModel
from packages.infrastructure.database.repositories.unit_of_work import SqlAlchemyUnitOfWork
from packages.infrastructure.transcription.deterministic_adapter import (
    DeterministicTranscriptionAdapter,
)
from packages.infrastructure.transcription.role_resolver import HeuristicSpeakerRoleResolver

TENANT = "ret-origin"
RECORDING_BUCKET = "sales-call-recordings"


class InMemoryStorage(StoragePort):
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    async def upload_object(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        self.objects[f"{bucket}/{key}"] = data

    async def upload_file(self, bucket: str, key: str, file_path: str, content_type: str) -> None:
        with open(file_path, "rb") as handle:
            self.objects[f"{bucket}/{key}"] = handle.read()

    async def download_object(self, bucket: str, key: str) -> bytes:
        return self.objects.get(f"{bucket}/{key}", b"")

    async def bucket_exists(self, bucket: str) -> bool:
        return True

    async def object_exists(self, bucket: str, key: str) -> bool:
        return f"{bucket}/{key}" in self.objects

    async def delete_object(self, bucket: str, key: str) -> None:
        self.objects.pop(f"{bucket}/{key}", None)

    async def get_presigned_url(self, bucket: str, key: str, expires_in_seconds: int = 3600) -> str:
        return f"https://in-memory/{bucket}/{key}"

    async def check_connection(self) -> bool:
        return True


class InMemoryQueue(QueuePort):
    def __init__(self):
        self.enqueued: list[tuple[str, dict[str, Any]]] = []

    async def enqueue(self, queue_name: str, payload: dict[str, Any]) -> None:
        self.enqueued.append((queue_name, payload))

    async def dequeue(self, queue_name: str, timeout: int = 0) -> dict[str, Any] | None:
        return None

    async def check_connection(self) -> bool:
        return True


def load_case(case_id: str) -> dict[str, Any]:
    """Materialise one labelled gold call, so the pipeline runs on a call with a known verdict."""
    gold_set = gold.load_gold_set()
    case = next(c for c in gold_set["cases"] if c["case_id"] == case_id)
    return gold.materialise_case(gold_set, case)


def write_fixture(scenario: dict[str, Any], path) -> str:
    """Write an ASR fixture whose utterances match the audio turns exactly."""
    utterances = [
        {
            "speaker_label": "SPEAKER_CH0" if role == "AGENT" else "SPEAKER_CH1",
            "start_ms": start_ms,
            "end_ms": end_ms,
            "text": text,
            "words": [],
        }
        for _order, role, start_ms, end_ms, text in scenario["segments"]
    ]
    payload = {
        "benchmark_scenario": "full-pipeline-e2e",
        "metadata": {"language": "en-AU"},
        "utterances": utterances,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


@pytest.fixture
async def pipeline(test_db_session, tmp_path):
    """Seed a retailer, the full checklist, a real WAV artifact, and a queued transcription job."""
    scenario = load_case("gold-002-rate-mismatch")
    now = datetime.fromisoformat(scenario["call_date"])
    uow = SqlAlchemyUnitOfWork(test_db_session)

    await uow.sales.save_retailer(Retailer(id=TENANT, code="RET_1", name="Origin Energy"))
    await uow.sales.save_campaign(
        Campaign(id="camp-e2e", code="CAMP_E2E", name="Inbound Energy", channel="INBOUND")
    )
    await uow.sales.save_agent(
        Agent(id="agt-e2e", staff_id="STF_E2E", name="Sarah Jenkins", email="s@test.com")
    )
    await uow.sales.save_lead(
        Lead(
            id="lead-3613790",
            customer_name=scenario["lead"]["customer_name"],
            customer_email=scenario["lead"]["customer_email"],
            phone="0412345678",
            state="VIC",
        )
    )
    await uow.sales.save_sale(
        Sale.create(
            "lead-3613790", TENANT, "camp-e2e", "agt-e2e", now,
            scenario["sale"]["details"], sale_id="sale-e2e",
        )
    )

    definitions, versions = build_check_library(ENERGY_RETAILER_CHECKLIST_V1, retailer_id=TENANT)
    for definition in definitions:
        await uow.checks.save_check_definition(definition)
    for version_list in versions.values():
        for version in version_list:
            await uow.checks.save_check_version(version)

    # Real audio: agent on channel 0, customer on channel 1, at the transcript's own timings.
    turns = [
        AudioTurn(channel=0 if role == "AGENT" else 1, start_ms=start_ms, end_ms=end_ms)
        for _order, role, start_ms, end_ms, _text in scenario["segments"]
    ]
    duration_ms = max(turn.end_ms for turn in turns) + 1000
    audio = synthesize_stereo_wav(turns, duration_ms=duration_ms)
    audio_hash = hashlib.sha256(audio).hexdigest()

    storage = InMemoryStorage()
    await storage.upload_object(RECORDING_BUCKET, "recordings/e2e.wav", audio, "audio/wav")

    test_db_session.add(
        ArtifactModel(
            id="art-audio-e2e",
            lead_id="lead-3613790",
            storage_key="recordings/e2e.wav",
            content_hash=audio_hash,
            content_type="audio/wav",
            size_bytes=len(audio),
            duration_seconds=duration_ms / 1000,
            metadata_json={"channels": 2, "sample_rate": 8000},
            created_at=now,
        )
    )
    await test_db_session.flush()

    await uow.transcripts.save_recording(
        Recording.create(
            sale_id="sale-e2e",
            artifact_id="art-audio-e2e",
            dialler_call_id="DIALLER_E2E",
            duration_seconds=duration_ms / 1000,
            call_date=now,
            recording_id="rec-e2e",
        )
    )

    test_db_session.add(
        PipelineJobModel(
            id="job-tx-e2e",
            recording_id="rec-e2e",
            stage="TRANSCRIBING",
            status=JobStatus.QUEUED.value,
            idempotency_key="key-tx-e2e",
            lease_generation=0,
            created_at=now,
            updated_at=now,
        )
    )
    await test_db_session.commit()

    fixture_path = write_fixture(scenario, tmp_path / "asr_fixture.json")

    @asynccontextmanager
    async def session_factory():
        yield test_db_session

    return {
        "audio": audio,
        "storage": storage,
        "queue": InMemoryQueue(),
        "session_factory": session_factory,
        "fixture_path": fixture_path,
        "scenario": scenario,
    }


async def run_pipeline(pipeline, test_db_session) -> str:
    """Run transcription then evaluation, returning the evaluation job id."""
    await execute_transcription_job(
        job_id="job-tx-e2e",
        worker_id="worker-e2e",
        correlation_id="corr-e2e",
        transcriber=DeterministicTranscriptionAdapter(fixture_path=pipeline["fixture_path"]),
        role_resolver=HeuristicSpeakerRoleResolver(),
        session_factory=pipeline["session_factory"],
        storage_adapter=pipeline["storage"],
        queue_adapter=pipeline["queue"],
    )
    test_db_session.expire_all()

    evaluation_messages = [m for m in pipeline["queue"].enqueued if m[0] == "queue:evaluation"]
    assert evaluation_messages, "transcription did not dispatch an evaluation job"
    eval_job_id = evaluation_messages[0][1]["job_id"]

    await execute_evaluation_job(
        job_id=eval_job_id,
        worker_id="worker-e2e",
        correlation_id="corr-e2e",
        session_factory=pipeline["session_factory"],
        queue_adapter=pipeline["queue"],
    )
    test_db_session.expire_all()
    return eval_job_id


class TestAudioIsReal:
    def test_generated_audio_is_valid_two_channel_pcm(self, pipeline):
        """The artifact is genuine audio the inspector accepts, not a placeholder byte string."""
        from io import BytesIO

        audio = pipeline["audio"]
        metadata = WavAudioInspector().inspect_stream(BytesIO(audio), len(audio))

        assert metadata.channels == 2
        assert metadata.bit_depth == 16
        assert metadata.duration_seconds > 60
        assert audio[:4] == b"RIFF"


@pytest.mark.asyncio
class TestFullPipeline:
    async def test_audio_reaches_a_gate_decision_with_grounded_evidence(
        self, pipeline, test_db_session
    ):
        await run_pipeline(pipeline, test_db_session)

        uow = SqlAlchemyUnitOfWork(test_db_session)
        lineage = await uow.evaluations.get_evaluation_lineage("sale-e2e", TENANT)

        assert lineage is not None
        gate = lineage["gate_decision"]
        # This labelled call quotes the wrong peak rate, so it must be held.
        assert gate["status"] == GateStatus.HELD.value
        assert gate["decision_reason_code"] == "CRITICAL_CHECK_FAILED"
        assert gate["auto_submitted"] is False

        failing = {
            r["check_code"]: r for r in lineage["results"] if r["result"] == "FAIL"
        }
        assert "FACTUAL_PEAK_RATE" in failing

        evidence = failing["FACTUAL_PEAK_RATE"]["evidence"][-1]
        assert evidence["observed_value"] == "28.6"
        assert evidence["expected_value"] == "31.9"
        # Grounded to a playable moment and to the rule version live on the call date.
        assert evidence["start_ms"] > 0
        assert failing["FACTUAL_PEAK_RATE"]["effective_from"] is not None

    async def test_whole_checklist_runs_not_just_a_subset(self, pipeline, test_db_session):
        await run_pipeline(pipeline, test_db_session)

        uow = SqlAlchemyUnitOfWork(test_db_session)
        lineage = await uow.evaluations.get_evaluation_lineage("sale-e2e", TENANT)
        codes = {r["check_code"] for r in lineage["results"]}

        assert any(code.startswith("VERBATIM_") for code in codes)
        assert any(code.startswith("FACTUAL_") for code in codes)
        assert any(code.startswith("BEHAVIOUR_") for code in codes)
        # Gas-only checks must not run on an electricity sale.
        assert "FACTUAL_MIRN" not in codes
        assert len(codes) >= 25

    async def test_held_sale_emits_a_crm_event_that_does_not_auto_submit(
        self, pipeline, test_db_session
    ):
        """The gate's decision has to reach the CRM, or nothing is actually blocked."""
        await run_pipeline(pipeline, test_db_session)

        result = await test_db_session.execute(select(OutboxEventModel))
        events = result.scalars().all()

        assert events, "no outbox event was written for the gate decision"
        held = [e for e in events if e.event_type == "SaleHeld"]
        assert held, [e.event_type for e in events]
        assert held[0].payload_json["auto_submitted"] is False

    async def test_both_worker_jobs_complete_and_release_their_leases(
        self, pipeline, test_db_session
    ):
        eval_job_id = await run_pipeline(pipeline, test_db_session)

        uow = SqlAlchemyUnitOfWork(test_db_session)
        for job_id in ("job-tx-e2e", eval_job_id):
            job = await uow.jobs.get_by_id(job_id)
            assert job.status == JobStatus.COMPLETED, job_id
            assert job.lease_until is None, job_id

    async def test_replaying_the_evaluation_is_idempotent(self, pipeline, test_db_session):
        eval_job_id = await run_pipeline(pipeline, test_db_session)

        before = await test_db_session.execute(select(GateDecisionModel))
        count_before = len(before.scalars().all())

        # A redelivered message must not produce a second gate decision.
        await execute_evaluation_job(
            job_id=eval_job_id,
            worker_id="worker-e2e-replay",
            correlation_id="corr-e2e",
            session_factory=pipeline["session_factory"],
            queue_adapter=pipeline["queue"],
        )
        test_db_session.expire_all()

        after = await test_db_session.execute(select(GateDecisionModel))
        assert len(after.scalars().all()) == count_before
