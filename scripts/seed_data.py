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
from packages.infrastructure.database.repositories import (
    SqlAlchemyCheckLibraryRepository,
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
        ret1 = Retailer(id="ret-origin", code="RETAILER_1", name="Origin Energy", vertical="ENERGY")
        ret2 = Retailer(id="ret-agl", code="RETAILER_2", name="AGL Energy", vertical="ENERGY")
        ret3 = Retailer(id="ret-ea", code="RETAILER_3", name="EnergyAustralia", vertical="ENERGY")
        for r in (ret1, ret2, ret3):
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
        tl = Agent(id="agent-tl-001", staff_id="TL_001", name="Michael Chang", email="m.chang@comparator.com.au")
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
            retailer_id="ret-origin",
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
            },
        )
        await sale_repo.save_sale(sale)

        # 6. Retailer 1 Checklist Definitions & Versions
        print("Seeding Retailer 1 Compliance Checklist...")
        checks = [
            (
                "chk-consent",
                "CHK_EXPLICIT_CONSENT",
                "Explicit Informed Consent (EIC)",
                CheckType.VERBATIM,
                True,
                {"verbatim_phrase": "Do you explicitly consent to switch your electricity to Origin Energy?"},
            ),
            (
                "chk-rates",
                "CHK_TARIFF_RATES",
                "Tariff Rates & Supply Charges Disclosure",
                CheckType.FACTUAL_MATCH,
                True,
                {"crm_field": "tariff_peak_c_kwh", "tolerance": 0.0},
            ),
            (
                "chk-email",
                "CHK_EMAIL_ACCURACY",
                "Customer Email Verification",
                CheckType.FACTUAL_MATCH,
                True,
                {"crm_field": "customer_email"},
            ),
            (
                "chk-cooling-off",
                "CHK_COOLING_OFF",
                "10-Day Cooling-off Period Notice",
                CheckType.VERBATIM,
                True,
                {"verbatim_phrase": "You have a 10 business day cooling off period"},
            ),
            (
                "chk-concession",
                "CHK_CONCESSION",
                "Energy Concession Eligibility Enquiry",
                CheckType.FACTUAL_MATCH,
                False,
                {"crm_field": "concession_applied"},
            ),
            (
                "chk-dead-air",
                "CHK_DEAD_AIR",
                "Dead Air / Silence Duration Threshold",
                CheckType.BEHAVIOUR,
                False,
                {"max_dead_air_seconds": 30},
            ),
            (
                "chk-disclosure",
                "CHK_CALL_DISCLOSURE",
                "Call Recording & Identity Disclosure",
                CheckType.VERBATIM,
                True,
                {"verbatim_phrase": "This call is being recorded for training and quality purposes"},
            ),
        ]

        for cid, code, name, ctype, is_crit, params in checks:
            chk_def = CheckDefinition(
                id=cid,
                check_code=code,
                name=name,
                check_type=ctype,
                is_critical=is_crit,
            )
            await chk_repo.save_check_definition(chk_def)

            chk_v = CheckVersion.create(
                check_id=cid,
                retailer_id="ret-origin",
                version_number=1,
                effective_from=effective_start,
                effective_to=None,
                parameters_json=params,
                version_id=f"{cid}-v1",
            )
            await chk_repo.save_check_version(chk_v)

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

        # 30-minute transcript segments including Brief 1 discrepancies
        segments = [
            TranscriptSegment.create(
                transcript_id="tx-3613790",
                segment_order=1,
                speaker=SpeakerType.AGENT,
                start_ms=5000,
                end_ms=12000,
                text="Hello, you are speaking with Sarah from Compare & Save. This call is being recorded for training and quality purposes.",
                segment_id="seg-3613790-01",
            ),
            TranscriptSegment.create(
                transcript_id="tx-3613790",
                segment_order=2,
                speaker=SpeakerType.CUSTOMER,
                start_ms=13000,
                end_ms=18000,
                text="Hi Sarah, I want to compare electricity plans for my home in Richmond.",
                segment_id="seg-3613790-02",
            ),
            TranscriptSegment.create(
                transcript_id="tx-3613790",
                segment_order=3,
                speaker=SpeakerType.AGENT,
                start_ms=495000,
                end_ms=505000,
                text="Do you currently hold any Australian government pension or healthcare concession card?",
                segment_id="seg-3613790-03",
            ),
            TranscriptSegment.create(
                transcript_id="tx-3613790",
                segment_order=4,
                speaker=SpeakerType.CUSTOMER,
                start_ms=506000,
                end_ms=510000,
                text="No, I don't have any concession card.",
                segment_id="seg-3613790-04",
            ),
            # 14:02 Rate quote discrepancy (Agent quotes 28.6c vs CRM 31.9c)
            TranscriptSegment.create(
                transcript_id="tx-3613790",
                segment_order=5,
                speaker=SpeakerType.AGENT,
                start_ms=842000,
                end_ms=855000,
                text="For the Origin Solar Boost plan, your electricity peak rate is 28.6 cents per kilowatt hour, with a daily supply charge of 115.5 cents.",
                segment_id="seg-3613790-05",
            ),
            TranscriptSegment.create(
                transcript_id="tx-3613790",
                segment_order=6,
                speaker=SpeakerType.CUSTOMER,
                start_ms=856000,
                end_ms=860000,
                text="Okay, 28.6 cents sounds good to me.",
                segment_id="seg-3613790-06",
            ),
            # 18:30 Dead air discrepancy (47 seconds silence)
            TranscriptSegment.create(
                transcript_id="tx-3613790",
                segment_order=7,
                speaker=SpeakerType.AGENT,
                start_ms=1110000,
                end_ms=1113000,
                text="Please hold on for a moment while I pull up the distributor details.",
                segment_id="seg-3613790-07",
            ),
            TranscriptSegment.create(
                transcript_id="tx-3613790",
                segment_order=8,
                speaker=SpeakerType.AGENT,
                start_ms=1160000,
                end_ms=1165000,
                text="Thank you so much for holding, I have confirmed your NMI is 6102123456.",
                segment_id="seg-3613790-08",
            ),
            # 22:10 Email confirmation discrepancy (Typo: gmial.com vs gmail.com)
            TranscriptSegment.create(
                transcript_id="tx-3613790",
                segment_order=9,
                speaker=SpeakerType.AGENT,
                start_ms=1330000,
                end_ms=1342000,
                text="I have recorded your confirmation email address as john.smith at gmial.com, that is g-m-i-a-l dot com.",
                segment_id="seg-3613790-09",
            ),
            TranscriptSegment.create(
                transcript_id="tx-3613790",
                segment_order=10,
                speaker=SpeakerType.CUSTOMER,
                start_ms=1343000,
                end_ms=1346000,
                text="Yes, that's fine.",
                segment_id="seg-3613790-10",
            ),
            # 26:45 Cooling-off notice
            TranscriptSegment.create(
                transcript_id="tx-3613790",
                segment_order=11,
                speaker=SpeakerType.AGENT,
                start_ms=1605000,
                end_ms=1615000,
                text="Please note you have a 10 business day cooling off period from the date you receive your welcome pack.",
                segment_id="seg-3613790-11",
            ),
            # 28:50 Explicit Informed Consent
            TranscriptSegment.create(
                transcript_id="tx-3613790",
                segment_order=12,
                speaker=SpeakerType.AGENT,
                start_ms=1730000,
                end_ms=1740000,
                text="Do you explicitly consent to switch your electricity to Origin Energy under the terms we discussed?",
                segment_id="seg-3613790-12",
            ),
            TranscriptSegment.create(
                transcript_id="tx-3613790",
                segment_order=13,
                speaker=SpeakerType.CUSTOMER,
                start_ms=1741000,
                end_ms=1745000,
                text="Yes, I consent to switch to Origin Energy.",
                segment_id="seg-3613790-13",
            ),
        ]
        await tr_repo.save_transcript(transcript, segments)
        await session.commit()

    await engine.dispose()
    print("Successfully seeded database with Phase 1 reference data and Lead 3613790!")


def main():
    parser = argparse.ArgumentParser(description="Seed SalesCall QA Reference Data")
    parser.add_argument("--sqlite", action="store_true", help="Use local SQLite database instead of PostgreSQL")
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
