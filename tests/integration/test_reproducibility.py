"""Lineage and reproducibility data contract integration test.

Verifies the foundational invariant:
Given:
  - same transcript artifact & hash
  - same transcript version (ASR + Diarization)
  - same CheckVersion
  - same model / provenance configuration
  - same prompt version
  - same policy version
Then:
  - evaluation lineage resolves to exactly the same immutable inputs and configuration.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from packages.domain.artifacts import Artifact
from packages.domain.check_library import CheckDefinition, CheckType, CheckVersion
from packages.domain.evaluation import (
    EvaluationResult,
    EvaluationResultStatus,
    EvaluationRun,
    Evidence,
    GateDecision,
)
from packages.domain.provenance import AIExecutionMetadata, AIProvenance
from packages.domain.retail import Agent, Campaign, Lead, Retailer, Sale
from packages.domain.state import GateStatus
from packages.domain.transcript import Recording, SpeakerType, Transcript, TranscriptSegment
from packages.infrastructure.database.models.artifacts import ArtifactModel
from packages.infrastructure.database.repositories import (
    SqlAlchemyCheckLibraryRepository,
    SqlAlchemyEvaluationRepository,
    SqlAlchemySaleRepository,
    SqlAlchemyTranscriptRepository,
)


def compute_evaluation_lineage_signature(
    transcript_artifact_hash: str,
    processor_version: str,
    checklist_version_id: str,
    provenance: AIProvenance,
) -> str:
    """Compute deterministic SHA-256 fingerprint representing the exact evaluation input contract."""
    payload = {
        "transcript_artifact_hash": transcript_artifact_hash,
        "processor_version": processor_version,
        "checklist_version_id": checklist_version_id,
        "model_provider": provenance.provider,
        "model_name": provenance.model,
        "model_version": provenance.model_version,
        "prompt_template_version": provenance.prompt_version,
        "pipeline_git_sha": provenance.pipeline_git_sha,
        "policy_version": provenance.policy_version,
        "temperature": provenance.temperature,
        "seed": provenance.seed,
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@pytest.mark.asyncio
async def test_evaluation_lineage_reproducibility_contract(test_db_session):
    sale_repo = SqlAlchemySaleRepository(test_db_session)
    tr_repo = SqlAlchemyTranscriptRepository(test_db_session)
    chk_repo = SqlAlchemyCheckLibraryRepository(test_db_session)
    eval_repo = SqlAlchemyEvaluationRepository(test_db_session)

    call_date = datetime(2026, 9, 18, 14, 0, 0, tzinfo=UTC)

    # 1. Ingest base entities
    ret = Retailer(id="ret-rep", code="RET_REPRO", name="Reproducibility Energy")
    camp = Campaign(id="camp-rep", code="CAMP_REP", name="Repro Campaign")
    agt = Agent(id="agt-rep", staff_id="STF_REP", name="Agent Repro", email="rep@test.com")
    lead = Lead(id="lead-rep", customer_name="Robert Repro", customer_email="robert@test.com", phone="0400111222")
    sale = Sale.create("lead-rep", "ret-rep", "camp-rep", "agt-rep", call_date, {}, sale_id="sale-rep-1")
    await sale_repo.save_retailer(ret)
    await sale_repo.save_campaign(camp)
    await sale_repo.save_agent(agt)
    await sale_repo.save_lead(lead)
    await sale_repo.save_sale(sale)

    # 2. Immutable Audio and Transcript Artifacts
    audio_bytes = b"RIFF_MOCK_WAV_AUDIO_DATA_FOR_CALL_REPRO"
    audio_art = Artifact.create(
        lead_id="lead-rep",
        storage_key="recordings/call_rep.wav",
        content_type="audio/wav",
        raw_content=audio_bytes,
        artifact_id="art-rep-audio",
    )
    tx_json = json.dumps([{"speaker": "AGENT", "text": "Welcome"}]).encode("utf-8")
    tx_art = Artifact.create(
        lead_id="lead-rep",
        storage_key="transcripts/call_rep.json",
        content_type="application/json",
        raw_content=tx_json,
        artifact_id="art-rep-tx",
    )
    test_db_session.add(
        ArtifactModel(
            id=audio_art.id,
            lead_id=audio_art.lead_id,
            storage_key=audio_art.storage_key,
            content_hash=audio_art.content_hash,
            content_type=audio_art.content_type,
            size_bytes=audio_art.size_bytes,
            created_at=audio_art.created_at,
        )
    )
    test_db_session.add(
        ArtifactModel(
            id=tx_art.id,
            lead_id=tx_art.lead_id,
            storage_key=tx_art.storage_key,
            content_hash=tx_art.content_hash,
            content_type=tx_art.content_type,
            size_bytes=tx_art.size_bytes,
            created_at=tx_art.created_at,
        )
    )
    await test_db_session.flush()

    # 3. Recording & Transcript
    rec = Recording.create("sale-rep-1", audio_art.id, "CALL_REP_999", 1800.0, call_date, recording_id="rec-rep-1")
    await tr_repo.save_recording(rec)

    tx = Transcript(
        id="tx-rep-1",
        recording_id="rec-rep-1",
        source_artifact_id=audio_art.id,
        output_artifact_id=tx_art.id,
        asr_provider="WHISPER",
        asr_model="whisper-large-v3",
        asr_model_version="2026.1",
        diarization_provider="PYANNOTE",
        diarization_version="3.1",
    )
    seg1 = TranscriptSegment.create("tx-rep-1", 1, SpeakerType.AGENT, 0, 3000, "Welcome to Origin.", segment_id="seg-rep-1")
    await tr_repo.save_transcript(tx, [seg1])

    # 4. Check Definition & Active Version
    chk = CheckDefinition(id="chk-rep-rates", check_code="CHK_RATES", name="Rates", check_type=CheckType.FACTUAL_MATCH, is_critical=True)
    await chk_repo.save_check_definition(chk)
    chk_v = CheckVersion.create("chk-rep-rates", "ret-rep", 1, call_date - timedelta(days=1), None, {"peak_rate": 31.9}, version_id="chk-v-rep-1")
    await chk_repo.save_check_version(chk_v)

    # 5. Fixed Provenance & Execution Configuration
    provenance = AIProvenance(
        provider="VERTEX_AI",
        model="gemini-1.5-pro",
        model_version="002",
        prompt_version="v2.1.0",
        check_version="chk-v-rep-1",
        policy_version="policy-2026.09",
        pipeline_git_sha="b74ac9183",
        temperature=0.0,
        seed=1337,
    )
    execution_meta = AIExecutionMetadata.create(
        started_at=call_date,
        completed_at=call_date + timedelta(milliseconds=950),
        input_tokens=500,
        output_tokens=100,
        estimated_cost_usd=0.002,
    )

    processor_version = Transcript.build_processor_version(
        tx.asr_model, tx.asr_model_version, tx.diarization_provider, tx.diarization_version
    )

    # Compute expected deterministic reproducibility signature
    sig1 = compute_evaluation_lineage_signature(
        transcript_artifact_hash=tx_art.content_hash,
        processor_version=processor_version,
        checklist_version_id=chk_v.id,
        provenance=provenance,
    )

    # Save Run, Result, Evidence, Gate
    eval_run = EvaluationRun.create(
        sale_id="sale-rep-1",
        transcript_id="tx-rep-1",
        checklist_version_id=chk_v.id,
        provenance=provenance,
        execution_metadata=execution_meta,
        run_id="run-rep-1",
    )
    result = EvaluationResult.create("run-rep-1", chk_v.id, EvaluationResultStatus.PASS, 0.99, 100.0, result_id="res-rep-1")
    evidence = Evidence.create("res-rep-1", "seg-rep-1", 0, 3000, "31.9c", "31.9c", "quoted 31.9c", evidence_id="ev-rep-1")
    await eval_repo.save_evaluation_run(eval_run, [result], [evidence])

    gate = GateDecision.create("sale-rep-1", "run-rep-1", GateStatus.PASSED, "policy-2026.09", "ALL_CRITICAL_CHECKS_PASSED", True, decision_id="gate-rep-1")
    await eval_repo.save_gate_decision(gate)

    # 6. Retrieve Lineage and Recompute Signature
    lineage = await eval_repo.get_evaluation_lineage("sale-rep-1")
    assert lineage is not None

    sig2 = compute_evaluation_lineage_signature(
        transcript_artifact_hash=tx_art.content_hash,
        processor_version=processor_version,
        checklist_version_id=lineage["checklist_version_id"],
        provenance=AIProvenance(
            provider=lineage["provenance"]["model_provider"],
            model=lineage["provenance"]["model_name"],
            model_version=lineage["provenance"]["model_version"],
            prompt_version=lineage["provenance"]["prompt_template_version"],
            check_version=lineage["checklist_version_id"],
            policy_version=lineage["provenance"]["policy_version"],
            pipeline_git_sha=lineage["provenance"]["pipeline_git_sha"],
            temperature=lineage["provenance"]["temperature"],
            seed=lineage["provenance"]["seed"],
        ),
    )

    # The data contract must produce an identical cryptographic reproducibility signature
    assert sig1 == sig2

    # A change in any input parameter (e.g. prompt_version or transcript hash) changes the signature
    tampered_provenance = AIProvenance(
        provider="VERTEX_AI",
        model="gemini-1.5-pro",
        model_version="002",
        prompt_version="v2.2.0-TAMPERED",
        check_version="chk-v-rep-1",
        policy_version="policy-2026.09",
        pipeline_git_sha="b74ac9183",
        temperature=0.0,
        seed=1337,
    )
    sig_tampered = compute_evaluation_lineage_signature(
        transcript_artifact_hash=tx_art.content_hash,
        processor_version=processor_version,
        checklist_version_id=chk_v.id,
        provenance=tampered_provenance,
    )
    assert sig1 != sig_tampered
