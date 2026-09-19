"""Seed reference data for SalesCall QA platform.

Populates:
- Retailers 1, 2, and 3 (Energy)
- Standard Campaign & Agents (including Team Lead)
- Retailer 1 complete compliance checklist (verbatim, factual, behavioral)
- Lead 3613790 sale, recording, and full 30-min transcript segments with Brief 1 discrepancy timestamps.
"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Add repository root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import packages.infrastructure.database.models  # noqa: F401
from packages.domain.check_library import CheckDefinition, CheckType, CheckVersion
from packages.evaluation.checklists.builder import build_check_library
from packages.evaluation.checklists.energy_retailer_v1 import ENERGY_RETAILER_CHECKLIST_V1
from packages.domain.retail import (
    Agent,
    Campaign,
    EnergyProductDetails,
    FuelType,
    Lead,
    Retailer,
    Sale,
)
from packages.domain.transcript import Recording, SpeakerType, Transcript, TranscriptSegment
from packages.infrastructure.config.settings import settings
from packages.infrastructure.database.base import Base
from packages.infrastructure.database.models.artifacts import ArtifactModel
from packages.domain.evaluation import (
    CheckOutcome,
    EvaluationResult,
    EvaluationRun,
    EvaluationRunStatus,
    Evidence,
    EvidenceType,
    GateDecision,
)
from packages.domain.provenance import AIExecutionMetadata, AIProvenance
from packages.domain.state import GateStatus
from packages.evaluation.engine import EvaluationOrchestrator
from packages.infrastructure.database.repositories import (
    SqlAlchemyCheckLibraryRepository,
    SqlAlchemyEvaluationRepository,
    SqlAlchemySaleRepository,
    SqlAlchemyTranscriptRepository,
)


async def seed(database_url: str) -> None:
    print(f"Connecting to database at {database_url}...")
    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        sale_repo = SqlAlchemySaleRepository(session)
        tr_repo = SqlAlchemyTranscriptRepository(session)
        chk_repo = SqlAlchemyCheckLibraryRepository(session)

        now = datetime(2026, 9, 18, 14, 0, 0, tzinfo=UTC)
        effective_start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

        # 1. Retailers
        print("Seeding Retailers...")
        ret0 = Retailer(id="retailer-cimet-01", code="RETAILER_CIMET_01", name="Origin Energy (Cimet)", vertical="ENERGY")
        ret_prod = Retailer(id="retailer-prod-001", code="RETAILER_PROD_001", name="Origin Energy (Production)", vertical="ENERGY")
        ret1 = Retailer(id="ret-origin", code="RETAILER_1", name="Origin Energy", vertical="ENERGY")
        ret2 = Retailer(id="ret-agl", code="RETAILER_2", name="AGL Energy", vertical="ENERGY")
        ret3 = Retailer(id="ret-ea", code="RETAILER_3", name="EnergyAustralia", vertical="ENERGY")
        for r in (ret0, ret_prod, ret1, ret2, ret3):
            await sale_repo.save_retailer(r)

        # 2. Campaign
        print("Seeding Campaign...")
        campaign = Campaign(
            id="camp-inbound-energy",
            code="CAMP_INBOUND_ENERGY",
            name="Residential Inbound Energy Comparator",
            channel="INBOUND",
        )
        await sale_repo.save_campaign(campaign)

        # 3. Agents
        print("Seeding Agents...")
        tl = Agent(
            id="agent-tl-001",
            staff_id="TL_001",
            name="Michael Chang",
            email="m.chang@comparator.com.au",
        )
        agent = Agent(
            id="agent-001",
            staff_id="AGT_001",
            name="Sarah Jenkins",
            email="s.jenkins@comparator.com.au",
            team_lead_id="agent-tl-001",
        )
        await sale_repo.save_agent(tl)
        await sale_repo.save_agent(agent)

        # 4. Lead 3613790
        print("Seeding Lead 3613790...")
        lead = Lead(
            id="lead-3613790",
            customer_name="John Smith",
            customer_email="john.smith@gmail.com",
            phone="0412345678",
            suburb="Richmond",
            state="VIC",
            postcode="3121",
            created_at=now,
        )
        await sale_repo.save_lead(lead)

        # 5. Sale 3613790
        print("Seeding Sale 3613790 with EnergyProductDetails...")
        energy_details = EnergyProductDetails(
            plan_code="ORIGIN_SOLAR_BOOST_2026",
            plan_name="Origin Solar Boost Electricity",
            fuel_type=FuelType.ELECTRICITY,
            tariff_peak_c_kwh=31.9,
            daily_supply_charge_cents=115.5,
            nmi="6102123456",
            cooling_off_days=10,
            concession_applied=False,
            life_support=False,
        )
        energy_details.validate()

        sale = Sale.create(
            sale_id="sale-3613790",
            lead_id="lead-3613790",
            retailer_id="retailer-cimet-01",
            campaign_id="camp-inbound-energy",
            agent_id="agent-001",
            sale_date=now,
            product_details={
                "plan_code": energy_details.plan_code,
                "plan_name": energy_details.plan_name,
                "fuel_type": energy_details.fuel_type.value,
                "tariff_peak_c_kwh": energy_details.tariff_peak_c_kwh,
                "daily_supply_charge_cents": energy_details.daily_supply_charge_cents,
                "nmi": energy_details.nmi,
                "cooling_off_days": energy_details.cooling_off_days,
                "concession_applied": energy_details.concession_applied,
                "life_support": energy_details.life_support,
                # Fields the expanded checklist resolves its expected values from.
                "supply_address": "12 Rose Street Richmond",
                "date_of_birth": "1985-03-12",
                "move_in_date": "2026-10-01",
                "gift_card_value": "100",
                "state": "VIC",
                "customer_type": "RESIDENTIAL",
            },
        )
        await sale_repo.save_sale(sale)

        # 6. Retailer Checklist Definitions & Versions
        # The full 30-check energy checklist is defined once in
        # packages/evaluation/checklists/energy_retailer_v1.py and shared by the seeder, the
        # integration tests, and the accuracy harness, so all three score identically.
        print("Seeding full energy retailer compliance checklist...")
        seen_definitions: set[str] = set()
        for ret_id in ("ret-origin", "retailer-cimet-01", "retailer-prod-001"):
            definitions, versions_by_id = build_check_library(
                entries=ENERGY_RETAILER_CHECKLIST_V1,
                retailer_id=ret_id,
                effective_from=effective_start,
            )
            for definition in definitions:
                if definition.id in seen_definitions:
                    continue
                await chk_repo.save_check_definition(definition)
                seen_definitions.add(definition.id)
            for versions in versions_by_id.values():
                for version in versions:
                    await chk_repo.save_check_version(version)

        print(
            f"  {len(seen_definitions)} checks "
            f"({sum(1 for e in ENERGY_RETAILER_CHECKLIST_V1 if e.is_critical)} critical) "
            f"across 3 retailers"
        )

        # 7. Audio and Transcript Artifacts
        print("Seeding Artifacts, Recording, and Utterance Segments...")
        audio_content = b"MOCK_WAV_AUDIO_LEAD_3613790_30MIN_STEREO"
        audio_hash = hashlib.sha256(audio_content).hexdigest()

        tx_data = {
            "recording_id": "rec-3613790",
            "call_id": "CALL_3613790_REC",
            "language": "en-AU",
            "lead_id": "lead-3613790",
        }
        tx_bytes = json.dumps(tx_data).encode("utf-8")
        tx_hash = hashlib.sha256(tx_bytes).hexdigest()

        art_audio = ArtifactModel(
            id="art-audio-3613790",
            lead_id="lead-3613790",
            storage_key="recordings/3613790_call.wav",
            content_hash=audio_hash,
            content_type="audio/wav",
            size_bytes=len(audio_content),
            duration_seconds=1800.0,
            metadata_json={"channels": 2, "sample_rate": 16000},
            created_at=now,
        )
        art_tx = ArtifactModel(
            id="art-tx-3613790",
            lead_id="lead-3613790",
            storage_key="transcripts/3613790_transcript.json",
            content_hash=tx_hash,
            content_type="application/json",
            size_bytes=len(tx_bytes),
            metadata_json={"model": "whisper-large-v3"},
            created_at=now,
        )
        session.add(art_audio)
        session.add(art_tx)
        await session.flush()

        # Recording
        recording = Recording.create(
            sale_id="sale-3613790",
            artifact_id="art-audio-3613790",
            dialler_call_id="CALL_3613790_REC",
            duration_seconds=1800.0,
            call_date=now,
            recording_id="rec-3613790",
        )
        await tr_repo.save_recording(recording)

        # Transcript
        transcript = Transcript(
            id="tx-3613790",
            recording_id="rec-3613790",
            source_artifact_id="art-audio-3613790",
            output_artifact_id="art-tx-3613790",
            asr_provider="WHISPER",
            asr_model="whisper-large-v3",
            asr_model_version="2026.1",
            diarization_provider="PYANNOTE",
            diarization_version="3.1",
            language="en-AU",
            created_at=now,
        )

        # 30-minute call reproducing the brief's worked example for Lead 3613790: every
        # critical criterion is met except the peak rate quoted at 14:02 and the email read
        # back at 22:10, plus a 47 second dead-air coaching note at 18:33.
        #
        # Each entry is (speaker, start_ms, end_ms, text).
        anchored_utterances = [
            (SpeakerType.AGENT, 5_000, 13_000,
             "Good afternoon, my name is Sarah Jenkins and I am calling on behalf of your energy comparison service."),
            (SpeakerType.AGENT, 13_500, 20_000,
             "This call is being recorded for training and quality assurance purposes."),
            (SpeakerType.AGENT, 20_500, 27_000,
             "Can I confirm that you are the account holder or authorised to make changes on this account?"),
            (SpeakerType.CUSTOMER, 27_500, 32_000,
             "Yes that's correct, John Smith speaking."),
            (SpeakerType.AGENT, 32_500, 40_000,
             "Thank you. I have your supply address as 12 Rose Street Richmond."),
            (SpeakerType.CUSTOMER, 40_500, 43_000, "Yes that's right."),
            (SpeakerType.AGENT, 43_500, 49_000, "Can I confirm your date of birth please?"),
            (SpeakerType.CUSTOMER, 49_500, 54_000, "It's the 12th of March 1985."),
            (SpeakerType.CUSTOMER, 60_000, 66_000,
             "I'm looking to compare electricity plans for my home in Richmond."),
            (SpeakerType.AGENT, 495_000, 505_000,
             "Do you currently hold any Australian government pension or healthcare concession card?"),
            (SpeakerType.CUSTOMER, 506_000, 510_000, "No, I don't have any concession card."),
            (SpeakerType.AGENT, 600_000, 608_000,
             "Does anyone at the premises rely on life support equipment?"),
            (SpeakerType.CUSTOMER, 608_500, 612_000, "No, nobody does."),
            (SpeakerType.AGENT, 700_000, 712_000,
             "This is the Origin Solar Boost Electricity plan, an electricity only product."),
            # 14:02 - rate quoted 28.6 c/kWh against a plan priced at 31.9 c/kWh.
            (SpeakerType.AGENT, 842_000, 855_000,
             "For the Origin Solar Boost Electricity plan, your peak rate is 28.6 cents per kilowatt hour."),
            (SpeakerType.AGENT, 856_000, 864_000,
             "The daily supply charge is 115.5 cents per day."),
            (SpeakerType.CUSTOMER, 865_000, 869_000, "Okay, that sounds good to me."),
            (SpeakerType.AGENT, 900_000, 912_000,
             "Compared to the Victorian Default Offer, this plan is estimated to cost less over twelve months."),
            (SpeakerType.AGENT, 950_000, 960_000,
             "Your connection date will be the 1st of October 2026."),
            (SpeakerType.AGENT, 1_000_000, 1_010_000,
             "You will also receive a 100 dollar gift card as part of this offer."),
            (SpeakerType.AGENT, 1_110_000, 1_113_000,
             "Please hold on for a moment while I pull up the distributor details."),
            # 18:33 - 47 seconds of dead air. Non-critical: a coaching note, never a hold.
            (SpeakerType.AGENT, 1_160_000, 1_168_000,
             "Thank you so much for holding, I have confirmed your NMI is 6102123456."),
            # 22:10 - email read back as gmial.com against a CRM record of gmail.com.
            (SpeakerType.AGENT, 1_330_000, 1_342_000,
             "I have recorded your confirmation email address as john.smith at gmial.com."),
            (SpeakerType.CUSTOMER, 1_343_000, 1_346_000, "Yes, that's fine."),
            (SpeakerType.AGENT, 1_605_000, 1_616_000,
             "You have a 10 business day cooling off period during which you may cancel without penalty."),
            (SpeakerType.AGENT, 1_650_000, 1_662_000,
             "We will send you a welcome pack containing the full terms and conditions and the energy price fact sheet."),
            (SpeakerType.AGENT, 1_730_000, 1_742_000,
             "Do you provide your explicit informed consent to proceed with this transfer?"),
            (SpeakerType.CUSTOMER, 1_743_000, 1_747_000, "Yes I do."),
            (SpeakerType.AGENT, 1_750_000, 1_758_000,
             "You are free to end this call at any time. Thank you for your time today."),
        ]

        # The anchored lines above sit at the timestamps the brief quotes, which leaves long
        # gaps between them. Real calls fill those minutes with conversation, so they are
        # bridged with filler turns; without this the dead-air check would fire on every gap
        # and bury the one deliberate 47 second silence.
        DEAD_AIR_WINDOW = (1_113_000, 1_160_000)
        FILLER_TURNS = [
            (SpeakerType.AGENT, "Let me take you through the next section of the comparison."),
            (SpeakerType.CUSTOMER, "Sure, that makes sense."),
            (SpeakerType.AGENT, "I'll just note that down on your account now."),
            (SpeakerType.CUSTOMER, "No problem, take your time."),
        ]

        def bridge_gaps(utterances, max_gap_ms=30_000, filler_ms=4_000):
            bridged = []
            for index, utterance in enumerate(utterances):
                bridged.append(utterance)
                if index + 1 >= len(utterances):
                    continue
                gap_start, gap_end = utterance[2], utterances[index + 1][1]
                if (gap_start, gap_end) == DEAD_AIR_WINDOW:
                    continue
                cursor, filler_index = gap_start, 0
                while gap_end - cursor > max_gap_ms:
                    role, text = FILLER_TURNS[filler_index % len(FILLER_TURNS)]
                    start = cursor + 2_000
                    bridged.append((role, start, min(start + filler_ms, gap_end - 1_000), text))
                    cursor = start + filler_ms
                    filler_index += 1
            return bridged

        segments = [
            TranscriptSegment.create(
                transcript_id="tx-3613790",
                segment_order=order,
                speaker=role,
                start_ms=start_ms,
                end_ms=end_ms,
                text=text,
                segment_id=f"seg-3613790-{order:03d}",
            )
            for order, (role, start_ms, end_ms, text) in enumerate(
                bridge_gaps(anchored_utterances), start=1
            )
        ]

        await tr_repo.save_transcript(transcript, segments)
        await session.commit()

        # 8. Run deterministic QA Evaluation for Lead 3613790
        print("Running Deterministic QA Evaluation for Lead 3613790...")
        eval_repo = SqlAlchemyEvaluationRepository(session)
        orch = EvaluationOrchestrator()
        check_defs = await chk_repo.get_check_definitions()
        check_versions = await chk_repo.get_all_check_versions_by_check_id(
            retailer_id=sale.retailer_id
        )

        provenance = AIProvenance(
            provider="deterministic-evaluator",
            model="qa-gate-engine",
            model_version="1.0.0",
            prompt_version="rules.v1",
            check_version="check_set.v1",
            policy_version="policy.v1",
            pipeline_git_sha="git-sha-phase4",
        )

        sale_data = {
            "id": sale.id,
            "retailer_id": sale.retailer_id,
            "customer_type": "RESIDENTIAL",
            "jurisdiction": "AU-VIC",
            "state": "VIC",
            "campaign_id": sale.campaign_id,
            "details": sale.product_details,
        }
        lead_data = {
            "id": lead.id,
            "customer_name": lead.customer_name,
            "email": lead.customer_email,
            "customer_email": lead.customer_email,
            "phone": lead.phone,
            "state": lead.state,
        }

        payload = orch.execute_evaluation(
            sale_id=sale.id,
            tenant_id=sale.retailer_id,
            transcript=transcript,
            segments=segments,
            recording=recording,
            check_definitions=check_defs,
            check_versions_by_id=check_versions,
            sale_data=sale_data,
            lead_data=lead_data,
            provenance=provenance,
            policy_version="policy.v1",
        )

        await eval_repo.save_evaluation_run(payload.run, payload.results, payload.evidences)
        await eval_repo.save_gate_decision(payload.gate_decision)

        # Build full results helper
        def build_clean_results(run_id: str, dead_air_fail: bool = False):
            all_res = [
                EvaluationResult(
                    id=f"res-{run_id}-consent",
                    evaluation_run_id=run_id,
                    check_id="chk-consent",
                    check_version_id="chk-consent-v1",
                    result=CheckOutcome.PASS,
                    confidence=0.99,
                    score_numeric=98.0,
                    is_critical=True,
                    reason_codes=["EXPLICIT_CONSENT_VERIFIED"],
                ),
                EvaluationResult(
                    id=f"res-{run_id}-cooling",
                    evaluation_run_id=run_id,
                    check_id="chk-cooling-off",
                    check_version_id="chk-cooling-off-v1",
                    result=CheckOutcome.PASS,
                    confidence=0.95,
                    score_numeric=100.0,
                    is_critical=True,
                    reason_codes=["COOLING_OFF_NOTIFIED"],
                ),
                EvaluationResult(
                    id=f"res-{run_id}-disc",
                    evaluation_run_id=run_id,
                    check_id="chk-disclosure",
                    check_version_id="chk-disclosure-v1",
                    result=CheckOutcome.PASS,
                    confidence=0.95,
                    score_numeric=100.0,
                    is_critical=True,
                    reason_codes=["RECORDING_DISCLOSURE_ACKNOWLEDGED"],
                ),
                EvaluationResult(
                    id=f"res-{run_id}-rates",
                    evaluation_run_id=run_id,
                    check_id="chk-rates",
                    check_version_id="chk-rates-v1",
                    result=CheckOutcome.PASS,
                    confidence=1.0,
                    score_numeric=100.0,
                    is_critical=True,
                    reason_codes=["EXACT_RATE_MATCH"],
                ),
                EvaluationResult(
                    id=f"res-{run_id}-email",
                    evaluation_run_id=run_id,
                    check_id="chk-email",
                    check_version_id="chk-email-v1",
                    result=CheckOutcome.PASS,
                    confidence=1.0,
                    score_numeric=100.0,
                    is_critical=True,
                    reason_codes=["EMAIL_VERIFIED"],
                ),
                EvaluationResult(
                    id=f"res-{run_id}-conc",
                    evaluation_run_id=run_id,
                    check_id="chk-concession",
                    check_version_id="chk-concession-v1",
                    result=CheckOutcome.PASS,
                    confidence=0.98,
                    score_numeric=100.0,
                    is_critical=False,
                    reason_codes=["CONCESSION_CONFIRMED"],
                ),
                EvaluationResult(
                    id=f"res-{run_id}-dead-air",
                    evaluation_run_id=run_id,
                    check_id="chk-dead-air",
                    check_version_id="chk-dead-air-v1",
                    result=CheckOutcome.FAIL if dead_air_fail else CheckOutcome.PASS,
                    confidence=0.72 if dead_air_fail else 0.99,
                    score_numeric=45.0 if dead_air_fail else 95.0,
                    is_critical=False,
                    reason_codes=["LONG_SILENCE_DETECTED"] if dead_air_fail else ["PACE_NORMAL"],
                ),
            ]
            return all_res

        # Seed for cimet and prod tenants
        for tenant_target in ("retailer-cimet-01", "retailer-prod-001"):
            suffix = "" if tenant_target == "retailer-cimet-01" else "-prod"

            # Lead 1 duplicate for prod if needed
            if tenant_target == "retailer-prod-001":
                prod_sale1 = Sale.create(
                    sale_id=f"sale-3613790{suffix}",
                    lead_id="lead-3613790",
                    retailer_id=tenant_target,
                    campaign_id="camp-inbound-energy",
                    agent_id="agent-001",
                    sale_date=now,
                    product_details=sale.product_details,
                )
                await sale_repo.save_sale(prod_sale1)
                prod_run1 = EvaluationRun(
                    id=f"run-3613790{suffix}",
                    sale_id=f"sale-3613790{suffix}",
                    transcript_id="tx-3613790",
                    checklist_version_id="chk-v1",
                    status=EvaluationRunStatus.SUCCEEDED,
                    provenance=provenance,
                    created_at=now,
                    tenant_id=tenant_target,
                )
                prod_gate1 = GateDecision.create(
                    sale_id=f"sale-3613790{suffix}",
                    evaluation_run_id=f"run-3613790{suffix}",
                    status=GateStatus.HELD,
                    policy_version="policy.v1",
                    decision_reason_code="CRITICAL_CHECK_FAILED",
                    decision_id=f"gate-3613790{suffix}",
                    reason_codes=["ONE_OR_MORE_CRITICAL_CHECKS_FAILED"],
                    blocking_check_ids=["chk-email", "chk-rates"],
                )
                await eval_repo.save_evaluation_run(prod_run1, payload.results, payload.evidences)
                await eval_repo.save_gate_decision(prod_gate1)

            # Lead 2: Emma Watson (PASSED)
            lead2_id = f"lead-3613791{suffix}"
            lead2 = Lead(
                id=lead2_id,
                customer_name="Emma Watson",
                customer_email="emma.watson@domain.com.au",
                phone="0423456789",
                suburb="Carlton",
                state="VIC",
                postcode="3053",
                created_at=now,
            )
            await sale_repo.save_lead(lead2)
            sale2 = Sale.create(
                sale_id=f"sale-3613791{suffix}",
                lead_id=lead2_id,
                retailer_id=tenant_target,
                campaign_id="camp-inbound-energy",
                agent_id="agent-001",
                sale_date=now,
                product_details=sale.product_details,
            )
            await sale_repo.save_sale(sale2)
            run2_id = f"run-3613791{suffix}"
            run2 = EvaluationRun(
                id=run2_id,
                sale_id=f"sale-3613791{suffix}",
                transcript_id="tx-3613790",
                checklist_version_id="chk-v1",
                status=EvaluationRunStatus.SUCCEEDED,
                provenance=provenance,
                created_at=now,
                tenant_id=tenant_target,
            )
            gate2 = GateDecision.create(
                sale_id=f"sale-3613791{suffix}",
                evaluation_run_id=run2_id,
                status=GateStatus.PASSED,
                policy_version="policy.v1",
                decision_reason_code="ALL_CHECKS_PASSED",
                decision_id=f"gate-3613791{suffix}",
                auto_submitted=True,
            )
            await eval_repo.save_evaluation_run(run2, build_clean_results(run2_id, dead_air_fail=False), [])
            await eval_repo.save_gate_decision(gate2)

            # Lead 3: David Miller (REVIEW_REQUIRED)
            lead3_id = f"lead-3613792{suffix}"
            lead3 = Lead(
                id=lead3_id,
                customer_name="David Miller",
                customer_email="d.miller@outlook.com",
                phone="0434567890",
                suburb="South Yarra",
                state="VIC",
                postcode="3141",
                created_at=now,
            )
            await sale_repo.save_lead(lead3)
            sale3 = Sale.create(
                sale_id=f"sale-3613792{suffix}",
                lead_id=lead3_id,
                retailer_id=tenant_target,
                campaign_id="camp-inbound-energy",
                agent_id="agent-001",
                sale_date=now,
                product_details=sale.product_details,
            )
            await sale_repo.save_sale(sale3)
            run3_id = f"run-3613792{suffix}"
            run3 = EvaluationRun(
                id=run3_id,
                sale_id=f"sale-3613792{suffix}",
                transcript_id="tx-3613790",
                checklist_version_id="chk-v1",
                status=EvaluationRunStatus.SUCCEEDED,
                provenance=provenance,
                created_at=now,
                tenant_id=tenant_target,
            )
            gate3 = GateDecision.create(
                sale_id=f"sale-3613792{suffix}",
                evaluation_run_id=run3_id,
                status=GateStatus.REVIEW_REQUIRED,
                policy_version="policy.v1",
                decision_reason_code="NON_CRITICAL_CHECK_UNCERTAINTY",
                decision_id=f"gate-3613792{suffix}",
                warnings=["Dead air exceeded threshold by 12s"],
            )
            await eval_repo.save_evaluation_run(run3, build_clean_results(run3_id, dead_air_fail=True), [])
            await eval_repo.save_gate_decision(gate3)

        await session.commit()

    await engine.dispose()
    print("Successfully seeded database with Phase 1 reference data, Lead 3613790, and evaluations!")


def main():
    parser = argparse.ArgumentParser(description="Seed SalesCall QA Reference Data")
    parser.add_argument(
        "--sqlite", action="store_true", help="Use local SQLite database instead of PostgreSQL"
    )
    parser.add_argument("--db-url", type=str, default="", help="Explicit database URL")
    args = parser.parse_args()

    if args.db_url:
        db_url = args.db_url
    elif args.sqlite:
        db_url = "sqlite+aiosqlite:///salescall_qa_seed.db"
    else:
        db_url = settings.database_url

    asyncio.run(seed(db_url))


if __name__ == "__main__":
    main()
