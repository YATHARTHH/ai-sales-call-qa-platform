"""Integration tests for FastAPI recording ingestion, playback, and scrubbing endpoints."""

import io
import wave
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app
from apps.api.routers.recordings import get_ingestion_service
from packages.application.services.ingestion_service import IngestionService
from packages.domain.retail import Agent, Campaign, Lead, Retailer, Sale
from packages.infrastructure.audio.wav_inspector import WavAudioInspector
from packages.infrastructure.database.repositories import (
    SqlAlchemySaleRepository,
    SqlAlchemyUnitOfWork,
)
from packages.infrastructure.database.session import get_db_session
from packages.infrastructure.storage.minio_storage import MinioStorageAdapter


def create_test_wav_bytes(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        num_frames = int(sample_rate * duration_seconds)
        wf.writeframes(b"\x00" * (num_frames * 2))
    return buf.getvalue()


class InMemoryStorage(MinioStorageAdapter):
    def __init__(self):
        self.objects = {}
    async def upload_object(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data
    async def upload_file(self, bucket: str, key: str, file_path: str, content_type: str) -> None:
        with open(file_path, "rb") as f:
            self.objects[key] = f.read()
    async def download_object(self, bucket: str, key: str) -> bytes:
        return self.objects[key]
    async def object_exists(self, bucket: str, key: str) -> bool:
        return key in self.objects
    async def get_presigned_url(self, bucket: str, key: str, expires_in_seconds: int = 3600) -> str:
        return f"http://localhost:9000/{bucket}/{key}?token=presigned"
    async def check_connection(self) -> bool:
        return True


@pytest.fixture
async def api_fixture(test_db_session):
    now = datetime.now(UTC)
    sale_repo = SqlAlchemySaleRepository(test_db_session)
    retailer = Retailer(id="ret-api-1", code="RET_ORIGIN", name="Origin Energy", vertical="ENERGY")
    await sale_repo.save_retailer(retailer)
    campaign = Campaign(id="camp-api-1", code="CAMP_INBOUND", name="Inbound")
    await sale_repo.save_campaign(campaign)
    agent = Agent(id="agent-api-1", staff_id="STF_001", name="Sarah", email="sarah@example.com")
    await sale_repo.save_agent(agent)
    lead = Lead(
        id="lead-api-1",
        customer_name="Jane Customer",
        customer_email="jane@example.com",
        phone="0412345678",
        suburb="Richmond",
        state="VIC",
        postcode="3121",
    )
    await sale_repo.save_lead(lead)
    sale = Sale.create(
        sale_id="sale-api-1",
        lead_id="lead-api-1",
        retailer_id="ret-api-1",
        campaign_id="camp-api-1",
        agent_id="agent-api-1",
        sale_date=now,
        product_details={"plan": "Solar Boost"},
    )
    await sale_repo.save_sale(sale)
    await test_db_session.commit()

    storage = InMemoryStorage()
    inspector = WavAudioInspector()
    uow = SqlAlchemyUnitOfWork(test_db_session)
    service = IngestionService(uow=uow, storage=storage, inspector=inspector, queue=None)

    async def override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[MinioStorageAdapter] = lambda: storage
    app.dependency_overrides[get_ingestion_service] = lambda: service

    yield test_db_session, storage

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_recordings_api_full_flow(api_fixture):
    session, storage = api_fixture
    wav_bytes = create_test_wav_bytes(duration_seconds=1.5)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. POST /api/v1/recordings/upload
        upload_resp = await client.post(
            "/api/v1/recordings/upload",
            data={
                "sale_id": "sale-api-1",
                "dialler_call_id": "call-api-1001",
                "call_date": "2026-09-18T10:00:00Z",
            },
            files={"file": ("test.wav", wav_bytes, "audio/wav")},
        )
        assert upload_resp.status_code == 201
        data = upload_resp.json()
        recording_id = data["recording_id"]
        artifact_id = data["artifact_id"]
        assert data["is_duplicate"] is False
        assert data["job_id"] is not None

        # 2. GET /api/v1/recordings/{id}
        get_resp = await client.get(f"/api/v1/recordings/{recording_id}")
        assert get_resp.status_code == 200
        rec_data = get_resp.json()
        assert rec_data["id"] == recording_id
        assert rec_data["artifact_id"] == artifact_id
        assert rec_data["dialler_call_id"] == "call-api-1001"

        # 3. GET /api/v1/recordings/{id}/presigned-url
        presigned_resp = await client.get(f"/api/v1/recordings/{recording_id}/presigned-url")
        assert presigned_resp.status_code == 200
        ps_data = presigned_resp.json()
        assert "presigned_url" in ps_data
        assert "token=presigned" in ps_data["presigned_url"]

        # 4. GET /api/v1/recordings/{id}/audio (Full download)
        audio_resp = await client.get(f"/api/v1/recordings/{recording_id}/audio")
        assert audio_resp.status_code == 200
        assert audio_resp.headers["content-type"] == "audio/wav"
        assert audio_resp.content == wav_bytes

        # 5. GET /api/v1/recordings/{id}/audio with Range header (HTTP 206 Partial Content)
        range_resp = await client.get(
            f"/api/v1/recordings/{recording_id}/audio",
            headers={"Range": "bytes=0-99"},
        )
        assert range_resp.status_code == 206
        assert range_resp.headers["content-range"].startswith("bytes 0-99/")
        assert len(range_resp.content) == 100
        assert range_resp.content == wav_bytes[:100]

        # 6. POST /api/v1/recordings/ingest (pre-staged S3 object)
        pre_key = "staged/lead3613790.wav"
        await storage.upload_object("recordings", pre_key, wav_bytes, "audio/wav")
        ingest_resp = await client.post(
            "/api/v1/recordings/ingest",
            json={
                "sale_id": "sale-api-1",
                "dialler_call_id": "dialler-prestaged-1",
                "storage_key": pre_key,
                "call_date": "2026-09-18T12:00:00Z",
            },
        )
        assert ingest_resp.status_code == 201
        ingest_data = ingest_resp.json()
        assert ingest_data["dialler_call_id"] == "dialler-prestaged-1"
        # It should reuse the artifact from the first upload because audio bytes are identical!
        assert ingest_data["artifact_id"] == artifact_id
