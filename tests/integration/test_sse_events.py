"""Integration tests for Server-Sent Events (SSE) notification streaming."""

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app


@pytest.mark.asyncio
async def test_sse_event_stream_connects_and_emits_initial_event():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/events/stream?tenant_id=retailer-cimet-01&single_event_only=true",
            headers={"X-Debug-Tenant-Id": "retailer-cimet-01"},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert "event: Connected" in response.text
        assert "retailer-cimet-01" in response.text
