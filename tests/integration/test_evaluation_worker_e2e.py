"""End-to-end integration tests for evaluation worker, Lead 3613790 benchmark, and lease fencing."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from apps.worker.tasks import execute_evaluation_job
from packages.domain.check_library import (
    CheckDefinition,
    CheckType,
    CheckVersion,
)
from packages.domain.jobs import PipelineJob
from packages.domain.provenance import AIProvenance
from packages.domain.retail import Lead, Retailer, Sale
from packages.domain.state import GateStatus
from packages.domain.transcript import (
    Recording,
    SpeakerType,
    Transcript,
    TranscriptAvailability,
    TranscriptSegment,
)
from packages.evaluation.engine import EvaluationOrchestrator
from packages.infrastructure.database.repositories.unit_of_work import SqlAlchemyUnitOfWork


def load_lead_3613790_fixture() -> dict:
    fixture_path = (
        Path(__file__).parent.parent / "fixtures" / "transcription" / "lead_3613790_benchmark.json"
    )
    with open(fixture_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.asyncio
async def test_lead_3613790_benchmark_regression_evaluation(test_db_session):
    """Authoritative benchmark test verifying Lead 3613790 fails rates, email, and dead air."""
    uow = SqlAlchemyUnitOfWork(test_db_session)
    now = datetime(2026, 9, 19, 10, 0, 0, tzinfo=UTC)

    # 1. Setup Retailer, Lead, Sale
    retailer = Retailer(id="ret-001", code="RET_001", name="Origin Energy")
    await uow.sales.save_retailer(retailer)

    lead = Lead(
        id="lead-3613790",
        customer_name="Jane Smith",
        customer_email="john.smith@gmail.com",  # Authoritative CRM email
        phone="0412345678",
        state="VIC",
    )
    await uow.sales.save_lead(lead)

    sale = Sale.create(
        lead_id=lead.id,
        retailer_id=retailer.id,
        campaign_id="camp-vic",
        agent_id="agent-sarah",
        sale_date=now,
        product_details={"fuel_type": "ELECTRICITY", "peak_rate": "31.9"},  # Authoritative expected rate
        sale_id="sale-3613790",
    )
    await uow.sales.save_sale(sale)

    # 2. Setup Recording & Transcript from benchmark fixture
    fixture = load_lead_3613790_fixture()
    rec = Recording.create(
        sale_id=sale.id,
        artifact_id="art-lead-3613790",
        dialler_call_id="call-lead-3613790",
        duration_seconds=fixture["metadata"]["call_duration_seconds"],
        call_date=now,
        recording_id="rec-3613790",
    )
    await uow.transcripts.save_recording(rec)

    transcript = Transcript(
        id="tx-3613790",
        recording_id=rec.id,
        source_artifact_id=rec.artifact_id,
        output_artifact_id="art-tx-3613790",
        asr_provider="whisper",
        asr_model="large-v3",
        asr_model_version="1.0",
        diarization_provider="pyannote",
        diarization_version="3.1",
        availability=TranscriptAvailability.AVAILABLE,
        audio_duration_ms=fixture["metadata"]["call_duration_ms"],
        created_at=now,
    )
    segments = []
    for i, utt in enumerate(fixture["utterances"], start=1):
        spk_label = utt["speaker_label"]
        b_role = (
            SpeakerType.AGENT
            if spk_label == "SPEAKER_00"
            else SpeakerType.CUSTOMER
        )
        segments.append(
            TranscriptSegment.create(
                transcript_id=transcript.id,
                segment_order=i,
                speaker_label=spk_label,
                business_role=b_role,
                start_ms=utt["start_ms"],
                end_ms=utt["end_ms"],
                text=utt["text"],
            )
        )
    await uow.transcripts.save_transcript(transcript, segments)

    # 3. Setup Compliance Check Definitions & Versions
    # Check 1: Peak Tariff Rate (Critical Factual Match)
    chk_rate = CheckDefinition(
        id="chk-rate",
        check_code="FACTUAL_PEAK_RATE",
        name="Peak Tariff Rate Match",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
    )
    v_rate = CheckVersion.create(
        check_id=chk_rate.id,
        retailer_id=retailer.id,
        version_number=1,
        effective_from=now,
        effective_to=None,
        parameters_json={
            "comparator": "DECIMAL",
            "crm_field": "details.peak_rate",
            "tolerance": "0.00",
            "keywords": ["rate", "cent", "peak", "kwh", "kilowatt"],
            "min_value": "5",
            "max_value": "500",
        },
    )
    # Check 2: Customer Email (Critical Factual Match)
    chk_email = CheckDefinition(
        id="chk-email",
        check_code="FACTUAL_EMAIL_CONFIRMATION",
        name="Customer Email Confirmation",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
    )
    v_email = CheckVersion.create(
        check_id=chk_email.id,
        retailer_id=retailer.id,
        version_number=1,
        effective_from=now,
        effective_to=None,
        parameters_json={"comparator": "EMAIL", "crm_field": "customer_email"},
    )
    # Check 3: Dead Air Silence (Non-Critical Behavioral Check)
    chk_silence = CheckDefinition(
        id="chk-silence",
        check_code="BEHAVIOUR_DEAD_AIR",
        name="Dead Air Silence Standard",
        check_type=CheckType.BEHAVIOUR,
        is_critical=False,
    )
    v_silence = CheckVersion.create(
        check_id=chk_silence.id,
        retailer_id=retailer.id,
        version_number=1,
        effective_from=now,
        effective_to=None,
        parameters_json={"max_silence_threshold_ms": 30000},
    )
    # Check 4: Verbatim EIC and Cooling Off (Critical Verbatim Match)
    chk_eic = CheckDefinition(
        id="chk-eic",
        check_code="VERBATIM_EIC_DISCLOSURE",
        name="Explicit Informed Consent & Cooling Off",
        check_type=CheckType.VERBATIM,
        is_critical=True,
    )
    v_eic = CheckVersion.create(
        check_id=chk_eic.id,
        retailer_id=retailer.id,
        version_number=1,
        effective_from=now,
        effective_to=None,
        parameters_json={
            "mandatory_concept_anchors": ["10 business day", "cooling off", "explicit", "consent"],
            "required_phrases": [
                "Please note you have a 10 business day cooling off period where you can cancel without penalty. Do you provide your explicit informed consent to proceed with this transfer?"
            ],
        },
    )

    for chk in (chk_rate, chk_email, chk_silence, chk_eic):
        await uow.checks.save_check_definition(chk)
    for ver in (v_rate, v_email, v_silence, v_eic):
        await uow.checks.save_check_version(ver)

    # 4. Create Evaluation PipelineJob in QUEUED status
    eval_job = PipelineJob.create(
        recording_id=rec.id,
        stage="EVALUATING",
        input_artifact_hash=transcript.output_artifact_id,
        processor_version="eval.v1",
    )
    await uow.jobs.save_job_idempotent(eval_job)
    await uow.commit()

    # 5. Execute Evaluation Worker Task
    session_factory = lambda: test_db_session
    await execute_evaluation_job(
        job_id=eval_job.id,
        worker_id="worker-qa-1",
        correlation_id="corr-lead-3613790",
        session_factory=session_factory,
    )

    # 6. Verify Lineage and Deterministic Gate Outcome
    lineage = await uow.evaluations.get_evaluation_lineage(sale.id)
    assert lineage is not None
    assert lineage["sale_id"] == sale.id

    # Gate decision must be HELD and auto_submitted False
    gate = lineage["gate_decision"]
    assert gate is not None
    assert gate["status"] == GateStatus.HELD.value
    assert gate["auto_submitted"] is False
    assert gate["decision_reason_code"] == "CRITICAL_CHECK_FAILED"

    # Blocking check IDs must contain rate and email checks
    blocking = gate["blocking_check_ids"]
    assert "chk-rate" in blocking
    assert "chk-email" in blocking

    # Results breakdown
    results_by_id = {r["check_id"]: r for r in lineage["results"]}

    # Rate check failed (28.6 vs 31.9)
    assert results_by_id["chk-rate"]["result"] == "FAIL"
    assert "FACTUAL_MISMATCH" in results_by_id["chk-rate"]["reason_codes"]

    # Email check failed (typo gmial.com vs gmail.com)
    assert results_by_id["chk-email"]["result"] == "FAIL"
    assert "FACTUAL_NEAR_MISS_MISMATCH" in results_by_id["chk-email"]["reason_codes"]

    # Dead air check failed (47s > 30s)
    assert results_by_id["chk-silence"]["result"] == "FAIL"
    assert "EXCESSIVE_DEAD_AIR" in results_by_id["chk-silence"]["reason_codes"]

    # Verbatim EIC passed
    assert results_by_id["chk-eic"]["result"] == "PASS"


@pytest.mark.asyncio
async def test_evaluation_clean_call_passes_gate(test_db_session):
    """Test clean compliant call passes all critical checks and auto-submits."""
    uow = SqlAlchemyUnitOfWork(test_db_session)
    now = datetime(2026, 9, 19, 10, 0, 0, tzinfo=UTC)

    retailer = Retailer(id="ret-clean", code="RET_CLEAN", name="Clean Energy")
    await uow.sales.save_retailer(retailer)

    lead = Lead(id="lead-clean", customer_name="Alice Walker", customer_email="alice@test.com", phone="0400000000", state="VIC")
    await uow.sales.save_lead(lead)

    sale = Sale.create(
        lead_id=lead.id,
        retailer_id=retailer.id,
        campaign_id="camp-clean",
        agent_id="agent-1",
        sale_date=now,
        product_details={"fuel_type": "ELECTRICITY", "peak_rate": "25.0"},
        sale_id="sale-clean",
    )
    await uow.sales.save_sale(sale)

    rec = Recording.create(
        sale_id=sale.id,
        artifact_id="art-clean",
        dialler_call_id="call-clean",
        duration_seconds=30.0,
        call_date=now,
        recording_id="rec-clean",
    )
    await uow.transcripts.save_recording(rec)

    transcript = Transcript(
        id="tx-clean",
        recording_id=rec.id,
        source_artifact_id=rec.artifact_id,
        output_artifact_id="art-tx-clean",
        asr_provider="whisper",
        asr_model="large-v3",
        asr_model_version="1.0",
        diarization_provider="pyannote",
        diarization_version="3.1",
        availability=TranscriptAvailability.AVAILABLE,
        audio_duration_ms=30000,
        created_at=now,
    )
    segments = [
        TranscriptSegment.create(
            transcript_id=transcript.id,
            segment_order=1,
            business_role=SpeakerType.AGENT,
            start_ms=0,
            end_ms=5000,
            text="Hello Alice, our electricity peak rate is 25.0 cents per kilowatt hour.",
        ),
        TranscriptSegment.create(
            transcript_id=transcript.id,
            segment_order=2,
            business_role=SpeakerType.AGENT,
            start_ms=5200,
            end_ms=10000,
            text="Your confirmation email will be sent to alice@test.com.",
        ),
        TranscriptSegment.create(
            transcript_id=transcript.id,
            segment_order=3,
            business_role=SpeakerType.AGENT,
            start_ms=10500,
            end_ms=18000,
            text="You have a 10 business day cooling off period. Do you give your explicit informed consent to proceed?",
        ),
        TranscriptSegment.create(
            transcript_id=transcript.id,
            segment_order=4,
            business_role=SpeakerType.CUSTOMER,
            start_ms=18500,
            end_ms=21000,
            text="Yes, I give my explicit consent.",
        ),
    ]
    await uow.transcripts.save_transcript(transcript, segments)

    chk_rate = CheckDefinition(id="chk-c-rate", check_code="FACTUAL_RATE", name="Rate", check_type=CheckType.FACTUAL_MATCH, is_critical=True)
    v_rate = CheckVersion.create(check_id="chk-c-rate", retailer_id=retailer.id, version_number=1, effective_from=now, effective_to=None, parameters_json={"comparator": "DECIMAL", "crm_field": "details.peak_rate", "keywords": ["rate", "cent", "peak", "kwh"], "min_value": "5", "max_value": "500"})

    chk_email = CheckDefinition(id="chk-c-email", check_code="FACTUAL_EMAIL", name="Email", check_type=CheckType.FACTUAL_MATCH, is_critical=True)
    v_email = CheckVersion.create(check_id="chk-c-email", retailer_id=retailer.id, version_number=1, effective_from=now, effective_to=None, parameters_json={"comparator": "EMAIL", "crm_field": "customer_email"})

    chk_eic = CheckDefinition(id="chk-c-eic", check_code="VERBATIM_EIC", name="EIC", check_type=CheckType.VERBATIM, is_critical=True)
    v_eic = CheckVersion.create(check_id="chk-c-eic", retailer_id=retailer.id, version_number=1, effective_from=now, effective_to=None, parameters_json={"mandatory_concept_anchors": ["10 business day", "cooling off", "explicit", "consent"]})

    for chk in (chk_rate, chk_email, chk_eic):
        await uow.checks.save_check_definition(chk)
    for ver in (v_rate, v_email, v_eic):
        await uow.checks.save_check_version(ver)

    eval_job = PipelineJob.create(
        recording_id=rec.id,
        stage="EVALUATING",
        input_artifact_hash=transcript.output_artifact_id,
        processor_version="eval.v1",
    )
    await uow.jobs.save_job_idempotent(eval_job)
    await uow.commit()

    await execute_evaluation_job(
        job_id=eval_job.id,
        worker_id="worker-qa-clean",
        correlation_id="corr-clean",
        session_factory=lambda: test_db_session,
    )

    lineage = await uow.evaluations.get_evaluation_lineage(sale.id)
    assert lineage is not None
    assert lineage["gate_decision"]["status"] == GateStatus.PASSED.value
    assert lineage["gate_decision"]["auto_submitted"] is True
    assert lineage["gate_decision"]["decision_reason_code"] == "ALL_CRITICAL_CHECKS_PASSED"


@pytest.mark.asyncio
async def test_evaluation_stale_worker_lease_loss_rolls_back(test_db_session):
    """Integration test verifying a stale worker cannot persist evaluation results after losing its lease."""
    uow = SqlAlchemyUnitOfWork(test_db_session)
    now = datetime(2026, 9, 19, 10, 0, 0, tzinfo=UTC)

    # 1. Setup sale, recording, transcript
    retailer = Retailer(id="ret-fence", code="RET_FENCE", name="Fence Energy")
    await uow.sales.save_retailer(retailer)

    sale = Sale.create(
        lead_id="lead-fence",
        retailer_id=retailer.id,
        campaign_id="camp-fence",
        agent_id="agent-1",
        sale_date=now,
        product_details={"fuel_type": "ELECTRICITY"},
        sale_id="sale-fence",
    )
    await uow.sales.save_sale(sale)

    rec = Recording.create(
        sale_id=sale.id,
        artifact_id="art-fence",
        dialler_call_id="call-fence",
        duration_seconds=30.0,
        call_date=now,
        recording_id="rec-fence",
    )
    await uow.transcripts.save_recording(rec)

    transcript = Transcript(
        id="tx-fence",
        recording_id=rec.id,
        source_artifact_id=rec.artifact_id,
        output_artifact_id="art-tx-fence",
        asr_provider="whisper",
        asr_model="large-v3",
        asr_model_version="1.0",
        diarization_provider="pyannote",
        diarization_version="3.1",
        availability=TranscriptAvailability.AVAILABLE,
        audio_duration_ms=30000,
        created_at=now,
    )
    seg = TranscriptSegment.create(
        transcript_id=transcript.id,
        segment_order=1,
        business_role=SpeakerType.AGENT,
        start_ms=0,
        end_ms=5000,
        text="Hello world",
    )
    await uow.transcripts.save_transcript(transcript, [seg])

    eval_job = PipelineJob.create(
        recording_id=rec.id,
        stage="EVALUATING",
        input_artifact_hash="art-tx-fence",
        processor_version="eval.v1",
    )
    await uow.jobs.save_job_idempotent(eval_job)
    await uow.commit()

    # 2. Worker 1 claims lease (generation = 1) with an immediately expired lease
    w1_job = await uow.jobs.claim_job_lease_atomic(eval_job.id, "worker-1", lease_duration_seconds=-1)
    assert w1_job is not None
    assert w1_job.lease_generation == 1
    await uow.commit()

    # 3. Lease is expired, so Worker 2 recovers and claims job (generation = 2)
    w2_job = await uow.jobs.claim_job_lease_atomic(eval_job.id, "worker-2", lease_duration_seconds=60)
    assert w2_job is not None
    assert w2_job.lease_generation == 2
    await uow.commit()

    # 4. Worker 1 finishes stale evaluation and attempts atomic fence completion
    fenced = await uow.jobs.complete_job_with_lease_fence(
        job_id=eval_job.id,
        worker_id="worker-1",
        lease_generation=1,  # Stale generation!
    )
    assert fenced is False  # Rejected!

    # 5. Verify Worker 1 commits 0 rows and database remains intact
    await uow.rollback()
    lineage = await uow.evaluations.get_evaluation_lineage(sale.id)
    assert lineage is None  # 0 evaluation rows persisted


def test_deterministic_evaluation_replay():
    """Verifies evaluating identical input snapshots produces bit-for-bit identical outputs."""
    now = datetime(2026, 9, 19, 10, 0, 0, tzinfo=UTC)
    orchestrator = EvaluationOrchestrator()

    rec = Recording.create(
        sale_id="sale-replay",
        artifact_id="art-replay",
        dialler_call_id="call-replay",
        duration_seconds=20.0,
        call_date=now,
    )
    tx = Transcript(
        id="tx-replay",
        recording_id=rec.id,
        source_artifact_id=rec.artifact_id,
        output_artifact_id="art-tx-replay",
        asr_provider="whisper",
        asr_model="large-v3",
        asr_model_version="1.0",
        diarization_provider="pyannote",
        diarization_version="3.1",
        availability=TranscriptAvailability.AVAILABLE,
        audio_duration_ms=20000,
    )
    segments = [
        TranscriptSegment.create(
            transcript_id="tx-replay",
            segment_order=1,
            business_role=SpeakerType.AGENT,
            start_ms=0,
            end_ms=4000,
            text="The rate is 25.0 cents per kilowatt hour.",
        ),
        TranscriptSegment.create(
            transcript_id="tx-replay",
            segment_order=2,
            business_role=SpeakerType.CUSTOMER,
            start_ms=4500,
            end_ms=7000,
            text="Yes, that is fine.",
        ),
    ]
    chk = CheckDefinition(
        id="chk-r", check_code="FACTUAL_RATE", name="Rate", check_type=CheckType.FACTUAL_MATCH, is_critical=True
    )
    ver = CheckVersion.create(
        check_id="chk-r", retailer_id="ret-r", version_number=1, effective_from=now, effective_to=None, parameters_json={"comparator": "DECIMAL", "crm_field": "details.peak_rate", "keywords": ["rate", "cent", "peak", "kwh"], "min_value": "5", "max_value": "500"}
    )
    sale_data = {"id": "sale-replay", "details": {"peak_rate": "25.0"}}
    lead_data = {"customer_name": "Bob"}
    provenance = AIProvenance("test", "test", "1.0", "v1", "chk.v1", "policy.v1")

    # Run 1
    run1 = orchestrator.execute_evaluation(
        sale_id="sale-replay",
        tenant_id="ret-r",
        transcript=tx,
        segments=segments,
        recording=rec,
        check_definitions=[chk],
        check_versions_by_id={"chk-r": [ver]},
        sale_data=sale_data,
        lead_data=lead_data,
        provenance=provenance,
    )

    # Run 2 on identical inputs
    run2 = orchestrator.execute_evaluation(
        sale_id="sale-replay",
        tenant_id="ret-r",
        transcript=tx,
        segments=segments,
        recording=rec,
        check_definitions=[chk],
        check_versions_by_id={"chk-r": [ver]},
        sale_data=sale_data,
        lead_data=lead_data,
        provenance=provenance,
    )

    # Invariants for deterministic replay:
    # 1. Identical snapshot content hash
    assert run1.snapshot.snapshot_content_hash == run2.snapshot.snapshot_content_hash
    # 2. Identical score
    assert run1.score_result.overall_score == run2.score_result.overall_score
    # 3. Identical gate decision status
    assert run1.gate_decision.status == run2.gate_decision.status
    assert run1.gate_decision.decision_reason_code == run2.gate_decision.decision_reason_code
    assert run1.gate_decision.blocking_check_ids == run2.gate_decision.blocking_check_ids
    # 4. Identical check outcome
    assert run1.results[0].result == run2.results[0].result
    assert run1.results[0].score_numeric == run2.results[0].score_numeric
