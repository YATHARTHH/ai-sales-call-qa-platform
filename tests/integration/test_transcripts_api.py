"""Integration tests for FastAPI transcripts router and tenant authorization."""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app
from packages.domain.jobs import JobStatus
from packages.domain.retail import Agent, Campaign, Lead, Retailer, Sale
from packages.domain.transcript import (
    Recording,
    SpeakerType,
    Transcript,
    TranscriptAvailability,
    TranscriptSegment,
)
from packages.infrastructure.database.models.artifacts import ArtifactModel
from packages.infrastructure.database.models.jobs import PipelineJobModel
from packages.infrastructure.database.repositories import (
    SqlAlchemySaleRepository,
    SqlAlchemyTranscriptRepository,
)
from packages.infrastructure.database.session import get_db_session


@pytest.fixture
async def setup_api_data(test_db_session):
    """Seed commercial entities, recording, transcript, and segments."""
    now = datetime.now(UTC)
    sale_repo = SqlAlchemySaleRepository(test_db_session)
    tr_repo = SqlAlchemyTranscriptRepository(test_db_session)

    # 1. Retailer, Campaign, Agent, Lead, Sale
    ret = Retailer(id="ret-api-1", code="RET_API_1", name="Tenant Alpha")
    camp = Campaign(id="camp-api-1", code="CAMP_API_1", name="Campaign 1")
    agt = Agent(id="agt-api-1", staff_id="STF_API_1", name="Agent 1", email="agt@test.com")
    lead = Lead(id="lead-api-1", customer_name="Customer 1", customer_email="c1@test.com", phone="0400000000")
    sale = Sale.create("lead-api-1", "ret-api-1", "camp-api-1", "agt-api-1", now, {}, sale_id="sale-api-1")

    await sale_repo.save_retailer(ret)
    await sale_repo.save_campaign(camp)
    await sale_repo.save_agent(agt)
    await sale_repo.save_lead(lead)
    await sale_repo.save_sale(sale)

    # 2. Artifacts & Recording
    audio_art = ArtifactModel(
        id="art-audio-api",
        lead_id="lead-api-1",
        storage_key="recordings/call_api.wav",
        content_hash="hash-audio-api",
        content_type="audio/wav",
        size_bytes=100000,
        metadata_json={},
        created_at=now,
    )
    transcript_art = ArtifactModel(
        id="art-tx-api",
        lead_id="lead-api-1",
        storage_key="transcripts/call_api.json",
        content_hash="hash-tx-api",
        content_type="application/json",
        size_bytes=5000,
        metadata_json={},
        created_at=now,
    )
    test_db_session.add(audio_art)
    test_db_session.add(transcript_art)
    await test_db_session.flush()

    recording = Recording.create(
        sale_id="sale-api-1",
        artifact_id="art-audio-api",
        dialler_call_id="CALL_API_001",
        duration_seconds=1800.0,
        call_date=now,
        recording_id="rec-api-1",
    )
    await tr_repo.save_recording(recording)

    # 3. Transcript
    transcript = Transcript(
        id="tx-api-1",
        recording_id="rec-api-1",
        source_artifact_id="art-audio-api",
        output_artifact_id="art-tx-api",
        transcription_key="transcription-key-api-001",
        transcription_identity="transcription:hash-audio:whisper-v1",
        availability=TranscriptAvailability.AVAILABLE,
        processor_version="whisper-large-v3@2026.1+pyannote@3.1",
        transcription_config_hash="conf-h1",
        diarization_config_hash="conf-h2",
        role_mapping_version="heuristic-v1",
        audio_duration_ms=1800000,
        transcribed_coverage_end_ms=1750000,
        leading_uncovered_ms=2000,
        trailing_uncovered_ms=50000,
        asr_provider="WHISPER",
        asr_model="whisper-large-v3",
        asr_model_version="2026.1",
        diarization_provider="PYANNOTE",
        diarization_version="3.1",
        language="en-AU",
        created_at=now,
    )

    segments = [
        TranscriptSegment.create(
            transcript_id="tx-api-1",
            segment_order=1,
            speaker_label="SPEAKER_00",
            business_role=SpeakerType.AGENT,
            role_confidence=0.98,
            start_ms=2000,
            end_ms=5000,
            text="Hello thank you for calling.",
            words_json=[{"word": "Hello", "start_ms": 2000, "end_ms": 2500, "confidence": 0.99}],
            segment_id="seg-api-1",
        ),
        TranscriptSegment.create(
            transcript_id="tx-api-1",
            segment_order=2,
            speaker_label="SPEAKER_01",
            business_role=SpeakerType.CUSTOMER,
            role_confidence=0.95,
            start_ms=5500,
            end_ms=9000,
            text="Hi I want to compare plans.",
            words_json=[{"word": "Hi", "start_ms": 5500, "end_ms": 5800, "confidence": 0.98}],
            segment_id="seg-api-2",
        ),
        TranscriptSegment.create(
            transcript_id="tx-api-1",
            segment_order=3,
            speaker_label="SPEAKER_00",
            business_role=SpeakerType.AGENT,
            role_confidence=0.99,
            start_ms=10000,
            end_ms=15000,
            text="Sure I can help you.",
            words_json=[{"word": "Sure", "start_ms": 10000, "end_ms": 10500, "confidence": 0.99}],
            segment_id="seg-api-3",
        ),
    ]

    behavior = {
        "audio_duration_ms": 1800000,
        "agent_talk_ms": 8000,
        "customer_talk_ms": 3500,
        "total_speech_ms": 11500,
        "agent_talk_percentage": 69.57,
        "customer_talk_percentage": 30.43,
        "conversational_occupancy_percentage": 0.64,
        "agent_words_per_minute": 120.0,
        "customer_words_per_minute": 102.8,
        "dead_air_gaps": [{"start_ms": 1110000, "end_ms": 1157000, "duration_ms": 47000}],
        "interruption_candidates": [],
    }

    await tr_repo.save_transcript(transcript, segments, behavior_json=behavior)
    await test_db_session.commit()
    return {"transcript_id": "tx-api-1", "recording_id": "rec-api-1", "tenant_id": "ret-api-1"}


@pytest.mark.asyncio
async def test_get_transcript_authorized_tenant(setup_api_data, test_db_session):
    """Authorized tenant gets 200 OK with transcript metadata."""
    app.dependency_overrides[get_db_session] = lambda: test_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/transcripts/{setup_api_data['transcript_id']}",
            headers={"X-Debug-Tenant-Id": setup_api_data["tenant_id"]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == setup_api_data["transcript_id"]
    assert data["availability"] == "AVAILABLE"
    assert data["transcription_key"] == "transcription-key-api-001"


@pytest.mark.asyncio
async def test_get_transcript_cross_tenant_rejected_with_404(setup_api_data, test_db_session):
    """Unauthorized cross-tenant request returns 404 to avoid information leakage."""
    app.dependency_overrides[get_db_session] = lambda: test_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/transcripts/{setup_api_data['transcript_id']}",
            headers={"X-Debug-Tenant-Id": "other-tenant-retailer"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_transcript_segments_pagination_and_word_redaction(setup_api_data, test_db_session):
    """Segments endpoint supports pagination and omits word arrays by default."""
    app.dependency_overrides[get_db_session] = lambda: test_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Default: include_words=false, limit=2
        resp = await client.get(
            f"/api/v1/transcripts/{setup_api_data['transcript_id']}/segments?offset=0&limit=2",
            headers={"X-Debug-Tenant-Id": setup_api_data["tenant_id"]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["offset"] == 0
    assert data["limit"] == 2
    # Words omitted by default
    assert data["items"][0]["words"] is None

    # Request with include_words=true
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp_words = await client.get(
            f"/api/v1/transcripts/{setup_api_data['transcript_id']}/segments?offset=0&limit=2&include_words=true",
            headers={"X-Debug-Tenant-Id": setup_api_data["tenant_id"]},
        )

    assert resp_words.status_code == 200
    words_data = resp_words.json()
    assert words_data["items"][0]["words"] is not None
    assert len(words_data["items"][0]["words"]) >= 1


@pytest.mark.asyncio
async def test_get_speech_behavior_metrics(setup_api_data, test_db_session):
    """Behavior metrics endpoint returns dead air gaps and talk time percentages."""
    app.dependency_overrides[get_db_session] = lambda: test_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/transcripts/{setup_api_data['transcript_id']}/behavior",
            headers={"X-Debug-Tenant-Id": setup_api_data["tenant_id"]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["audio_duration_ms"] == 1800000
    assert data["agent_talk_percentage"] == 69.57
    assert len(data["dead_air_gaps"]) == 1
    assert data["dead_air_gaps"][0]["duration_ms"] == 47000


@pytest.mark.asyncio
async def test_get_recording_transcript_lookup(setup_api_data, test_db_session):
    """Recording-to-transcript lookup returns transcript when available."""
    app.dependency_overrides[get_db_session] = lambda: test_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/recordings/{setup_api_data['recording_id']}/transcript",
            headers={"X-Debug-Tenant-Id": setup_api_data["tenant_id"]},
        )

    assert resp.status_code == 200
    assert resp.json()["id"] == setup_api_data["transcript_id"]


@pytest.mark.asyncio
async def test_get_recording_transcript_409_when_transcribing(setup_api_data, test_db_session):
    """Returns 409 Conflict if transcription job is currently RUNNING for recording without transcript."""
    now = datetime.now(UTC)
    tr_repo = SqlAlchemyTranscriptRepository(test_db_session)

    # Create recording without transcript
    recording2 = Recording.create(
        sale_id="sale-api-1",
        artifact_id="art-audio-api",
        dialler_call_id="CALL_API_002",
        duration_seconds=600.0,
        call_date=now,
        recording_id="rec-running",
    )
    await tr_repo.save_recording(recording2)

    running_job = PipelineJobModel(
        id="job-running-1",
        recording_id="rec-running",
        stage="TRANSCRIBING",
        status=JobStatus.RUNNING.value,
        idempotency_key="key-running-1",
        created_at=now,
        updated_at=now,
    )
    test_db_session.add(running_job)
    await test_db_session.commit()

    app.dependency_overrides[get_db_session] = lambda: test_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/recordings/rec-running/transcript",
            headers={"X-Debug-Tenant-Id": setup_api_data["tenant_id"]},
        )

    assert resp.status_code == 409
    assert "in progress" in resp.json()["detail"]
