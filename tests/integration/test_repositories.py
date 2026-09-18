"""Integration tests for SQLAlchemy repository adapters and database constraints."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from packages.domain.audit import ActorType, AuditEvent
from packages.domain.check_library import CheckDefinition, CheckType, CheckVersion
from packages.domain.evaluation import (
    EvaluationResult,
    EvaluationResultStatus,
    EvaluationRun,
    Evidence,
    GateDecision,
    HumanReview,
    HumanReviewAction,
)
from packages.domain.provenance import AIExecutionMetadata, AIProvenance
from packages.domain.retail import Agent, Campaign, Lead, Retailer, Sale, SaleStatus
from packages.domain.state import GateStatus
from packages.domain.transcript import Recording, SpeakerType, Transcript, TranscriptSegment
from packages.infrastructure.database.models.artifacts import ArtifactModel
from packages.infrastructure.database.repositories import (
    SqlAlchemyAuditRepository,
    SqlAlchemyCheckLibraryRepository,
    SqlAlchemyEvaluationRepository,
    SqlAlchemySaleRepository,
    SqlAlchemyTranscriptRepository,
)


@pytest.mark.asyncio
async def test_sale_repository_lifecycle(test_db_session):
    now = datetime.now(UTC)
    repo = SqlAlchemySaleRepository(test_db_session)

    # 1. Retailer
    retailer = Retailer(id="ret-1", code="RET_ORIGIN", name="Origin Energy", vertical="ENERGY")
    await repo.save_retailer(retailer)
    fetched_ret = await repo.get_retailer("ret-1")
    assert fetched_ret is not None
    assert fetched_ret.code == "RET_ORIGIN"

    # 2. Campaign & Agent
    campaign = Campaign(id="camp-1", code="CAMP_INBOUND", name="Inbound Energy")
    await repo.save_campaign(campaign)

    agent = Agent(id="agent-1", staff_id="STF_001", name="Sarah Agent", email="sarah@example.com")
    await repo.save_agent(agent)

    # 3. Lead
    lead = Lead(
        id="lead-1",
        customer_name="John Smith",
        customer_email="john@example.com",
        phone="0412345678",
        suburb="Richmond",
        state="VIC",
        postcode="3121",
    )
    await repo.save_lead(lead)
    fetched_lead = await repo.get_lead("lead-1")
    assert fetched_lead is not None
    assert fetched_lead.customer_name == "John Smith"

    # 4. Sale
    sale = Sale.create(
        sale_id="sale-1",
        lead_id="lead-1",
        retailer_id="ret-1",
        campaign_id="camp-1",
        agent_id="agent-1",
        sale_date=now,
        product_details={"plan": "Solar Boost", "tariff_c_kwh": 31.9},
    )
    await repo.save_sale(sale)
    fetched_sale = await repo.get_sale("sale-1")
    assert fetched_sale is not None
    assert fetched_sale.status == SaleStatus.PENDING_QA
    assert fetched_sale.product_details["tariff_c_kwh"] == 31.9


@pytest.mark.asyncio
async def test_transcript_repository_lifecycle(test_db_session):
    now = datetime.now(UTC)
    sale_repo = SqlAlchemySaleRepository(test_db_session)
    tr_repo = SqlAlchemyTranscriptRepository(test_db_session)

    # Setup parent records
    ret = Retailer(id="ret-tr", code="RET_TR", name="Test Retailer")
    camp = Campaign(id="camp-tr", code="CAMP_TR", name="Test Campaign")
    agt = Agent(id="agt-tr", staff_id="STF_TR", name="Test Agent", email="t@test.com")
    lead = Lead(id="lead-tr", customer_name="Jane Doe", customer_email="jane@test.com", phone="0400000000")
    sale = Sale.create("lead-tr", "ret-tr", "camp-tr", "agt-tr", now, {}, sale_id="sale-tr")
    await sale_repo.save_retailer(ret)
    await sale_repo.save_campaign(camp)
    await sale_repo.save_agent(agt)
    await sale_repo.save_lead(lead)
    await sale_repo.save_sale(sale)

    # Audio & Output Artifacts in DB
    audio_art = ArtifactModel(
        id="art-audio-1",
        lead_id="lead-tr",
        storage_key="recordings/call1.wav",
        content_hash="hash-audio-1",
        content_type="audio/wav",
        size_bytes=1024000,
        metadata_json={},
        created_at=now,
    )
    transcript_art = ArtifactModel(
        id="art-tx-1",
        lead_id="lead-tr",
        storage_key="transcripts/tx1.json",
        content_hash="hash-tx-1",
        content_type="application/json",
        size_bytes=4096,
        metadata_json={},
        created_at=now,
    )
    test_db_session.add(audio_art)
    test_db_session.add(transcript_art)
    await test_db_session.flush()

    # Recording
    recording = Recording.create(
        sale_id="sale-tr",
        artifact_id="art-audio-1",
        dialler_call_id="DIALLER_CALL_001",
        duration_seconds=1800.0,
        call_date=now,
        recording_id="rec-1",
    )
    await tr_repo.save_recording(recording)
    fetched_rec = await tr_repo.get_recording("rec-1")
    assert fetched_rec is not None
    assert fetched_rec.dialler_call_id == "DIALLER_CALL_001"

    # Transcript and Utterances
    transcript = Transcript(
        id="tx-1",
        recording_id="rec-1",
        source_artifact_id="art-audio-1",
        output_artifact_id="art-tx-1",
        asr_provider="WHISPER",
        asr_model="whisper-large-v3",
        asr_model_version="2026.1",
        diarization_provider="PYANNOTE",
        diarization_version="3.1",
    )
    segments = [
        TranscriptSegment.create(
            transcript_id="tx-1",
            segment_order=1,
            speaker=SpeakerType.AGENT,
            start_ms=0,
            end_ms=4500,
            text="Hello thanks for calling.",
            segment_id="seg-1",
        ),
        TranscriptSegment.create(
            transcript_id="tx-1",
            segment_order=2,
            speaker=SpeakerType.CUSTOMER,
            start_ms=4600,
            end_ms=8000,
            text="Hi I would like to compare rates.",
            segment_id="seg-2",
        ),
    ]
    await tr_repo.save_transcript(transcript, segments)

    fetched_tx = await tr_repo.get_transcript("tx-1")
    assert fetched_tx is not None
    assert fetched_tx.asr_model == "whisper-large-v3"

    fetched_segs = await tr_repo.get_transcript_segments("tx-1")
    assert len(fetched_segs) == 2
    assert fetched_segs[0].segment_order == 1
    assert fetched_segs[1].segment_order == 2


@pytest.mark.asyncio
async def test_check_library_lifecycle_and_resolution(test_db_session):
    sale_repo = SqlAlchemySaleRepository(test_db_session)
    check_repo = SqlAlchemyCheckLibraryRepository(test_db_session)

    ret = Retailer(id="ret-chk", code="RET_CHK", name="Check Retailer")
    await sale_repo.save_retailer(ret)

    check_def = CheckDefinition(
        id="chk-consent",
        check_code="CHK_EXPLICIT_CONSENT",
        name="Explicit Informed Consent",
        check_type=CheckType.VERBATIM,
        is_critical=True,
    )
    await check_repo.save_check_definition(check_def)

    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 6, 1, tzinfo=UTC)
    t2 = datetime(2026, 6, 2, tzinfo=UTC)

    v1 = CheckVersion.create(
        check_id="chk-consent",
        retailer_id="ret-chk",
        version_number=1,
        effective_from=t0,
        effective_to=t1,
        parameters_json={"script": "Do you consent to this agreement?"},
        version_id="ver-c1",
    )
    v2 = CheckVersion.create(
        check_id="chk-consent",
        retailer_id="ret-chk",
        version_number=2,
        effective_from=t2,
        effective_to=None,
        parameters_json={"script": "Do you explicitly consent to switch with Origin Energy?"},
        version_id="ver-c2",
    )
    await check_repo.save_check_version(v1)
    await check_repo.save_check_version(v2)

    # Query versions
    all_v = await check_repo.get_check_versions("ret-chk", "CHK_EXPLICIT_CONSENT")
    assert len(all_v) == 2

    # Resolve for call in March 2026 -> Version 1
    call_march = datetime(2026, 3, 15, tzinfo=UTC)
    active_march = await check_repo.get_retailer_checklist("ret-chk", call_march)
    assert len(active_march) == 1
    assert active_march[0].version_number == 1

    # Resolve for call in August 2026 -> Version 2
    call_aug = datetime(2026, 8, 1, tzinfo=UTC)
    active_aug = await check_repo.get_retailer_checklist("ret-chk", call_aug)
    assert len(active_aug) == 1
    assert active_aug[0].version_number == 2


@pytest.mark.asyncio
async def test_evaluation_repository_and_full_lineage(test_db_session):
    now = datetime.now(UTC)
    sale_repo = SqlAlchemySaleRepository(test_db_session)
    tr_repo = SqlAlchemyTranscriptRepository(test_db_session)
    check_repo = SqlAlchemyCheckLibraryRepository(test_db_session)
    eval_repo = SqlAlchemyEvaluationRepository(test_db_session)

    # 1. Base entities
    ret = Retailer(id="ret-ev", code="RET_EV", name="Eval Retailer")
    camp = Campaign(id="camp-ev", code="CAMP_EV", name="Eval Campaign")
    agt = Agent(id="agt-ev", staff_id="STF_EV", name="Eval Agent", email="ev@test.com")
    tl = Agent(id="tl-ev", staff_id="STF_TL", name="Team Lead", email="tl@test.com")
    lead = Lead(id="lead-ev", customer_name="Alex Taylor", customer_email="alex@test.com", phone="0411111111")
    sale = Sale.create("lead-ev", "ret-ev", "camp-ev", "agt-ev", now, {}, sale_id="sale-ev")
    await sale_repo.save_retailer(ret)
    await sale_repo.save_campaign(camp)
    await sale_repo.save_agent(agt)
    await sale_repo.save_agent(tl)
    await sale_repo.save_lead(lead)
    await sale_repo.save_sale(sale)

    # 2. Artifacts & Recording & Transcript
    audio_art = ArtifactModel(
        id="art-ev-audio",
        lead_id="lead-ev",
        storage_key="rec.wav",
        content_hash="hash-ev-audio",
        content_type="audio/wav",
        size_bytes=2048,
        metadata_json={},
        created_at=now,
    )
    tx_art = ArtifactModel(
        id="art-ev-tx",
        lead_id="lead-ev",
        storage_key="tx.json",
        content_hash="hash-ev-tx",
        content_type="application/json",
        size_bytes=1024,
        metadata_json={},
        created_at=now,
    )
    test_db_session.add(audio_art)
    test_db_session.add(tx_art)
    await test_db_session.flush()

    rec = Recording.create("sale-ev", "art-ev-audio", "CALL_EV_001", 600.0, now, recording_id="rec-ev")
    await tr_repo.save_recording(rec)

    tx = Transcript(
        id="tx-ev",
        recording_id="rec-ev",
        source_artifact_id="art-ev-audio",
        output_artifact_id="art-ev-tx",
        asr_provider="WHISPER",
        asr_model="large-v3",
        asr_model_version="v1",
        diarization_provider="PYANNOTE",
        diarization_version="v3",
    )
    seg = TranscriptSegment.create("tx-ev", 1, SpeakerType.AGENT, 1000, 5000, "Your peak rate is 28.6 cents.", segment_id="seg-ev-1")
    await tr_repo.save_transcript(tx, [seg])

    # 3. Check definition & version
    chk = CheckDefinition(id="chk-ev-rates", check_code="CHK_RATES", name="Rate Verification", check_type=CheckType.FACTUAL_MATCH, is_critical=True)
    await check_repo.save_check_definition(chk)
    chk_v = CheckVersion.create("chk-ev-rates", "ret-ev", 1, now - timedelta(days=10), None, {}, version_id="chk-v-ev")
    await check_repo.save_check_version(chk_v)

    # 4. Evaluation Run + Results + Grounded Evidence
    provenance = AIProvenance(
        provider="VERTEX_AI",
        model="gemini-1.5-pro",
        model_version="002",
        prompt_version="v2.1.0",
        check_version="chk-v-ev",
        policy_version="policy-2026.09",
        pipeline_git_sha="abcdef1234567890",
        temperature=0.0,
        seed=42,
    )
    execution_meta = AIExecutionMetadata.create(
        started_at=now,
        completed_at=now + timedelta(milliseconds=1200),
        input_tokens=850,
        output_tokens=150,
        estimated_cost_usd=0.0035,
    )
    eval_run = EvaluationRun.create(
        sale_id="sale-ev",
        transcript_id="tx-ev",
        checklist_version_id="chk-v-ev",
        provenance=provenance,
        execution_metadata=execution_meta,
        run_id="run-ev-1",
    )
    eval_result = EvaluationResult.create(
        evaluation_run_id="run-ev-1",
        check_version_id="chk-v-ev",
        result=EvaluationResultStatus.FAIL,
        confidence=0.98,
        score_numeric=0.0,
        result_id="res-ev-1",
    )
    evidence = Evidence.create(
        evaluation_result_id="res-ev-1",
        transcript_segment_id="seg-ev-1",
        start_ms=1000,
        end_ms=5000,
        expected_value="31.9c/kWh",
        observed_value="28.6c/kWh",
        transcript_excerpt="Your peak rate is 28.6 cents.",
        ai_explanation="Agent quoted 28.6c/kWh which contradicts the CRM tariff of 31.9c/kWh.",
        evidence_id="ev-1",
    )

    await eval_repo.save_evaluation_run(eval_run, [eval_result], [evidence])

    # 5. Gate Decision
    gate = GateDecision.create(
        sale_id="sale-ev",
        evaluation_run_id="run-ev-1",
        status=GateStatus.HELD,
        policy_version="policy-2026.09",
        decision_reason_code="CRITICAL_CHECK_FAILURE",
        auto_submitted=False,
        decision_id="gate-ev-1",
    )
    await eval_repo.save_gate_decision(gate)

    # 6. Human Review (Override / Confirmation)
    review = HumanReview.create(
        gate_decision_id="gate-ev-1",
        reviewer_id="tl-ev",
        action=HumanReviewAction.CONFIRM_HOLD,
        reason_notes="Confirmed rate misquote at 14:02. Sale must remain held.",
        review_id="rev-ev-1",
    )
    await eval_repo.save_human_review(review)

    # 7. Verify unbroken Lineage Retrieval
    lineage = await eval_repo.get_evaluation_lineage("sale-ev")
    assert lineage is not None
    assert lineage["sale_id"] == "sale-ev"
    assert lineage["transcript_id"] == "tx-ev"
    assert lineage["provenance"]["model_name"] == "gemini-1.5-pro"
    assert lineage["execution_metadata"]["latency_ms"] == 1200
    assert len(lineage["results"]) == 1
    assert lineage["results"][0]["result"] == "FAIL"
    assert lineage["results"][0]["evidence"][0]["transcript_excerpt"] == "Your peak rate is 28.6 cents."
    assert lineage["gate_decision"]["status"] == "HELD"
    assert len(lineage["human_reviews"]) == 1
    assert lineage["human_reviews"][0]["action"] == "CONFIRM_HOLD"


@pytest.mark.asyncio
async def test_audit_repository_append_only(test_db_session):
    audit_repo = SqlAlchemyAuditRepository(test_db_session)

    e1 = AuditEvent.record(
        entity_type="SALE",
        entity_id="sale-audit-1",
        action="CREATED",
        actor_type=ActorType.SYSTEM,
        actor_id="system-worker",
        correlation_id="corr-123",
        payload_json={"status": "PENDING_QA"},
    )
    e2 = AuditEvent.record(
        entity_type="SALE",
        entity_id="sale-audit-1",
        action="GATE_HELD",
        actor_type=ActorType.AI,
        actor_id="gemini-qa-gate",
        correlation_id="corr-123",
        payload_json={"reason": "RATE_MISQUOTE"},
    )
    await audit_repo.record_event(e1)
    await audit_repo.record_event(e2)

    events = await audit_repo.get_events_for_entity("SALE", "sale-audit-1")
    assert len(events) == 2
    assert events[0].action == "CREATED"
    assert events[1].action == "GATE_HELD"
    assert events[1].actor_type == ActorType.AI


@pytest.mark.asyncio
async def test_database_constraints_enforced(test_db_session):
    now = datetime.now(UTC)
    """Verify database-level constraints enforce critical invariants (Safeguard #1)."""

    # 1. Duplicate dialler_call_id constraint on recordings
    sale_repo = SqlAlchemySaleRepository(test_db_session)
    ret = Retailer(id="ret-ck", code="RET_CK", name="CK Ret")
    camp = Campaign(id="camp-ck", code="CAMP_CK", name="CK Camp")
    agt = Agent(id="agt-ck", staff_id="STF_CK", name="CK Agent", email="ck@ck.com")
    lead = Lead(id="lead-ck", customer_name="CK Lead", customer_email="ck@ck.com", phone="0400000001")
    sale = Sale.create("lead-ck", "ret-ck", "camp-ck", "agt-ck", now, {}, sale_id="sale-ck")
    await sale_repo.save_retailer(ret)
    await sale_repo.save_campaign(camp)
    await sale_repo.save_agent(agt)
    await sale_repo.save_lead(lead)
    await sale_repo.save_sale(sale)

    art = ArtifactModel(
        id="art-ck-1",
        lead_id="lead-ck",
        storage_key="rec.wav",
        content_hash="ck-hash",
        content_type="audio/wav",
        size_bytes=100,
        metadata_json={},
        created_at=now,
    )
    test_db_session.add(art)
    await test_db_session.flush()

    tr_repo = SqlAlchemyTranscriptRepository(test_db_session)
    r1 = Recording.create("sale-ck", "art-ck-1", "DIALLER_UNIQUE_KEY", 100.0, now, recording_id="rec-ck-1")
    await tr_repo.save_recording(r1)

    # Second insert with identical dialler_call_id must violate unique constraint
    r2 = Recording.create("sale-ck", "art-ck-1", "DIALLER_UNIQUE_KEY", 120.0, now, recording_id="rec-ck-2")
    with pytest.raises(IntegrityError):
        await tr_repo.save_recording(r2)
    await test_db_session.rollback()
