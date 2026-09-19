"""Integration tests for FastAPI evaluations router, queue, lineage, and human review."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from apps.api.dependencies import get_current_principal, get_queue
from apps.api.main import app
from packages.application.ports.queue import QueuePort
from packages.domain.evaluation import (
    CheckExecutionResult,
    CheckOutcome,
    EvaluationInputSnapshot,
    EvaluationResult,
    EvaluationRun,
    EvaluationRunStatus,
    Evidence,
    EvidenceType,
    GateDecision,
    GateReasonCode,
    GroundedEvidence,
)
from packages.domain.provenance import AIExecutionMetadata, AIProvenance
from packages.domain.retail import Agent, Campaign, Lead, Retailer, Sale
from packages.domain.state import GateStatus
from packages.domain.transcript import Recording, SpeakerType, Transcript, TranscriptAvailability, TranscriptSegment
from packages.infrastructure.database.models.artifacts import ArtifactModel
from packages.infrastructure.database.models.evaluations import OutboxEventModel
from packages.infrastructure.database.repositories import (
    SqlAlchemyEvaluationRepository,
    SqlAlchemySaleRepository,
    SqlAlchemyTranscriptRepository,
)
from packages.infrastructure.database.session import get_db_session


class FakeQueue(QueuePort):
    def __init__(self):
        self.messages: list[tuple[str, dict]] = []

    async def enqueue(self, job_name: str, payload: dict) -> str:
        self.messages.append((job_name, payload))
        return "msg-fake-id"

    async def check_connection(self) -> bool:
        return True


@pytest.fixture
async def seeded_eval_data(test_db_session):
    """Seed commercial entities, transcripts, and an evaluated sale."""
    now = datetime.now(UTC)
    sale_repo = SqlAlchemySaleRepository(test_db_session)
    tr_repo = SqlAlchemyTranscriptRepository(test_db_session)
    eval_repo = SqlAlchemyEvaluationRepository(test_db_session)

    # 1. Retailers
    r1 = Retailer(id="ret-tenant-1", code="TENANT_1", name="Tenant One")
    r2 = Retailer(id="ret-tenant-2", code="TENANT_2", name="Tenant Two")
    await sale_repo.save_retailer(r1)
    await sale_repo.save_retailer(r2)

    c1 = Campaign(id="camp-1", code="CAMP_1", name="Campaign 1")
    await sale_repo.save_campaign(c1)

    agt = Agent(id="agt-1", staff_id="STF_1", name="Agent 1", email="agent@test.com")
    await sale_repo.save_agent(agt)

    # Leads & Sales
    lead1 = Lead(id="lead-1", customer_name="Alice Smith", customer_email="alice@test.com", phone="0412345678")
    lead2 = Lead(id="lead-2", customer_name="Bob Jones", customer_email="bob@test.com", phone="0487654321")
    await sale_repo.save_lead(lead1)
    await sale_repo.save_lead(lead2)

    sale1 = Sale.create("lead-1", "ret-tenant-1", "camp-1", "agt-1", now, {}, sale_id="sale-eval-1")
    sale2 = Sale.create("lead-2", "ret-tenant-2", "camp-1", "agt-1", now, {}, sale_id="sale-eval-2")
    await sale_repo.save_sale(sale1)
    await sale_repo.save_sale(sale2)

    # Recordings & Transcripts for sale 1
    rec1 = Recording.create(
        sale_id="sale-eval-1",
        artifact_id="art-audio-1",
        dialler_call_id="CALL_001",
        duration_seconds=120.0,
        call_date=now,
        recording_id="rec-eval-1",
    )
    await tr_repo.save_recording(rec1)

    tx1 = Transcript(
        id="tx-eval-1",
        recording_id="rec-eval-1",
        source_artifact_id="art-audio-1",
        output_artifact_id="art-tx-1",
        transcription_key="key-eval-1",
        transcription_identity="tx:call001:whisper",
        availability=TranscriptAvailability.AVAILABLE,
        processor_version="whisper-v3",
        transcription_config_hash="h1",
        diarization_config_hash="h2",
        role_mapping_version="r1",
        audio_duration_ms=120000,
        transcribed_coverage_end_ms=120000,
        leading_uncovered_ms=0,
        trailing_uncovered_ms=0,
        asr_provider="WHISPER",
        asr_model="whisper-large-v3",
        asr_model_version="2026.1",
        diarization_provider="PYANNOTE",
        diarization_version="3.1",
        language="en-AU",
        created_at=now,
    )
    segments1 = [
        TranscriptSegment.create(
            transcript_id="tx-eval-1",
            segment_order=1,
            speaker_label="SPEAKER_00",
            business_role=SpeakerType.AGENT,
            role_confidence=0.98,
            start_ms=1000,
            end_ms=5000,
            text="Hello Alice, we offer 28.5 cents per kilowatt hour.",
            segment_id="seg-eval-1",
        )
    ]
    await tr_repo.save_transcript(tx1, segments1)

    # Evaluation Run 1 for sale 1 (status HELD)
    prov = AIProvenance(
        provider="deterministic",
        model="tier-evaluator",
        model_version="1.0",
        prompt_version="1.0",
        check_version="chk-v1",
        pipeline_git_sha="git-sha-test",
        policy_version="policy.v1",
        temperature=0.0,
        seed=42,
    )
    run1 = EvaluationRun(
        id="run-eval-1",
        sale_id="sale-eval-1",
        transcript_id="tx-eval-1",
        checklist_version_id="chk-v1",
        status=EvaluationRunStatus.SUCCEEDED,
        provenance=prov,
        created_at=now,
        execution_metadata=AIExecutionMetadata.create(started_at=now, completed_at=now, input_tokens=100, output_tokens=50),
        tenant_id="ret-tenant-1",
    )
    res1 = EvaluationResult(
        id="res-eval-1",
        evaluation_run_id="run-eval-1",
        check_id="chk-rate",
        check_version_id="chk-v1",
        result=CheckOutcome.FAIL,
        confidence=1.0,
        score_numeric=0.0,
        is_critical=True,
        reason_codes=["FACTUAL_TARIFF_RATE_MISMATCH"],
    )
    ev1 = Evidence(
        id="ev-eval-1",
        evaluation_result_id="res-eval-1",
        transcript_segment_id="seg-eval-1",
        transcript_id="tx-eval-1",
        speaker="SPEAKER_00",
        evidence_type=EvidenceType.CONTRADICTING,
        start_ms=1000,
        end_ms=5000,
        transcript_excerpt="we offer 28.5 cents",
        expected_value="31.2 c/kWh",
        observed_value="28.5 c/kWh",
    )
    await eval_repo.save_evaluation_run(run1, [res1], [ev1])

    gate1 = GateDecision.create(
        sale_id="sale-eval-1",
        evaluation_run_id="run-eval-1",
        status=GateStatus.HELD,
        policy_version="policy.v1",
        decision_reason_code="TARIFF_MISMATCH",
        decision_id="gate-eval-1",
        reason_codes=["TARIFF_MISMATCH"],
    )
    await eval_repo.save_gate_decision(gate1)

    # Seed an evaluated sale for tenant 2 (status PASSED)
    run2 = EvaluationRun(
        id="run-eval-2",
        sale_id="sale-eval-2",
        transcript_id="tx-eval-1",
        checklist_version_id="chk-v1",
        status=EvaluationRunStatus.SUCCEEDED,
        provenance=prov,
        created_at=now,
        tenant_id="ret-tenant-2",
    )
    gate2 = GateDecision.create(
        sale_id="sale-eval-2",
        evaluation_run_id="run-eval-2",
        status=GateStatus.PASSED,
        policy_version="policy.v1",
        decision_reason_code="ALL_CRITICAL_CHECKS_PASSED",
        decision_id="gate-eval-2",
    )
    await eval_repo.save_evaluation_run(run2, [], [])
    await eval_repo.save_gate_decision(gate2)

    await test_db_session.commit()
    return {
        "tenant_1": "ret-tenant-1",
        "tenant_2": "ret-tenant-2",
        "sale_1": "sale-eval-1",
        "sale_2": "sale-eval-2",
        "gate_1": "gate-eval-1",
        "gate_2": "gate-eval-2",
    }


@pytest.mark.asyncio
async def test_get_evaluation_queue_tenant_isolation(seeded_eval_data, test_db_session):
    """Queue returns only the records belonging to the authenticated tenant."""
    app.dependency_overrides[get_db_session] = lambda: test_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Tenant 1 request
        resp1 = await client.get(
            "/api/v1/evaluations/queue",
            headers={"X-Debug-Tenant-Id": seeded_eval_data["tenant_1"]},
        )
        assert resp1.status_code == 200
        items1 = resp1.json()
        assert len(items1) == 1
        assert items1[0]["sale_id"] == seeded_eval_data["sale_1"]
        assert items1[0]["status"] == "HELD"

        # Tenant 2 request
        resp2 = await client.get(
            "/api/v1/evaluations/queue",
            headers={"X-Debug-Tenant-Id": seeded_eval_data["tenant_2"]},
        )
        assert resp2.status_code == 200
        items2 = resp2.json()
        assert len(items2) == 1
        assert items2[0]["sale_id"] == seeded_eval_data["sale_2"]
        assert items2[0]["status"] == "PASSED"


@pytest.mark.asyncio
async def test_get_evaluation_lineage_authorized(seeded_eval_data, test_db_session):
    """Authorized tenant gets comprehensive evaluation lineage including checks and grounded quotes."""
    app.dependency_overrides[get_db_session] = lambda: test_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/evaluations/{seeded_eval_data['sale_1']}",
            headers={"X-Debug-Tenant-Id": seeded_eval_data["tenant_1"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sale_id"] == seeded_eval_data["sale_1"]
        assert data["gate_decision"]["status"] == "HELD"
        assert len(data["results"]) == 1
        assert data["results"][0]["check_id"] == "chk-rate"
        assert data["results"][0]["result"] == "FAIL"
        assert len(data["results"][0]["evidence"]) == 1
        assert data["results"][0]["evidence"][0]["observed_value"] == "28.5 c/kWh"


@pytest.mark.asyncio
async def test_get_evaluation_lineage_cross_tenant_rejected_with_404(seeded_eval_data, test_db_session):
    """Cross-tenant lineage query is strictly rejected with 404 to avoid information leakage."""
    app.dependency_overrides[get_db_session] = lambda: test_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/evaluations/{seeded_eval_data['sale_1']}",
            headers={"X-Debug-Tenant-Id": seeded_eval_data["tenant_2"]},
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_submit_human_review_override_to_pass(seeded_eval_data, test_db_session):
    """Submitting OVERRIDE_TO_PASS updates gate decision to PASSED and records review."""
    app.dependency_overrides[get_db_session] = lambda: test_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/evaluations/{seeded_eval_data['gate_1']}/review",
            headers={
                "X-Debug-Tenant-Id": seeded_eval_data["tenant_1"],
                "X-Debug-User-Id": "qa-reviewer-01",
            },
            json={
                "action": "OVERRIDE_TO_PASS",
                "reason_notes": "Customer accepted revised rate later in call after correction.",
                "reviewer_role": "QA_MANAGER",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_gate_status"] == "PASSED"
        assert data["action"] == "OVERRIDE_TO_PASS"

    # Verify state in DB
    uow_repo = SqlAlchemyEvaluationRepository(test_db_session)
    lineage = await uow_repo.get_evaluation_lineage(seeded_eval_data["sale_1"], seeded_eval_data["tenant_1"])
    assert lineage["gate_decision"]["status"] == "PASSED"


@pytest.mark.asyncio
async def test_submit_human_review_cancel_sale_creates_outbox_event(seeded_eval_data, test_db_session):
    """Submitting CANCEL_SALE updates status to CANCEL_REQUESTED and writes an outbox event in same transaction."""
    app.dependency_overrides[get_db_session] = lambda: test_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/evaluations/{seeded_eval_data['gate_1']}/review",
            headers={
                "X-Debug-Tenant-Id": seeded_eval_data["tenant_1"],
                "X-Debug-User-Id": "compliance-lead-02",
            },
            json={
                "action": "CANCEL_SALE",
                "reason_notes": "Fatal disclosure omission. Cancelling transaction immediately.",
                "reviewer_role": "COMPLIANCE_DIRECTOR",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_gate_status"] == "HELD"
        assert data["sale_disposition"] == "CANCEL_REQUESTED"

    # Verify outbox event written in DB
    stmt = select(OutboxEventModel).where(OutboxEventModel.aggregate_id == seeded_eval_data["sale_1"])
    res = await test_db_session.execute(stmt)
    outbox_entry = res.scalars().first()
    assert outbox_entry is not None
    assert outbox_entry.event_type == "CancellationRequested"
    assert outbox_entry.published_at is None  # PENDING = not yet published
    assert outbox_entry.payload_json["action"] == "CANCEL_SALE"


@pytest.mark.asyncio
async def test_submit_human_review_cross_tenant_rejected_with_404(seeded_eval_data, test_db_session):
    """Submitting a review for a gate decision of another tenant is rejected with 404."""
    app.dependency_overrides[get_db_session] = lambda: test_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/evaluations/{seeded_eval_data['gate_1']}/review",
            headers={
                "X-Debug-Tenant-Id": seeded_eval_data["tenant_2"],  # Tenant 2 trying to review Tenant 1's decision
                "X-Debug-User-Id": "qa-hacker",
            },
            json={
                "action": "OVERRIDE_TO_PASS",
                "reason_notes": "Unauthorized attempt to override.",
                "reviewer_role": "QA_MANAGER",
            },
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rerun_evaluation_queues_job(seeded_eval_data, test_db_session):
    """Triggering a rerun enqueues a new evaluation job and records an audit event."""
    fake_queue = FakeQueue()
    app.dependency_overrides[get_db_session] = lambda: test_db_session
    app.dependency_overrides[get_queue] = lambda: fake_queue

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/evaluations/{seeded_eval_data['sale_1']}/rerun",
            headers={
                "X-Debug-Tenant-Id": seeded_eval_data["tenant_1"],
                "X-Debug-User-Id": "admin-user",
            },
            json={
                "mode": "FULL_REPROCESSING",
                "reason": "Updated checklist version effective today.",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "QUEUED"
        assert data["sale_id"] == seeded_eval_data["sale_1"]
        assert data["mode"] == "FULL_REPROCESSING"

    # Verify message enqueued
    assert len(fake_queue.messages) == 1
    queue_name, payload = fake_queue.messages[0]
    assert queue_name == "queue:evaluation"
    assert payload["job_id"] == data["job_id"]
