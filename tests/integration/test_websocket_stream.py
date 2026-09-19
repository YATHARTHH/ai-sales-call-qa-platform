"""Integration tests for live WebSocket audio stream monitor."""

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def test_websocket_stream_flow() -> None:
    """Test connecting to live WebSocket stream endpoint, sending chunks, and receiving live compliance alerts."""
    with client.websocket_connect("/api/v1/events/ws/stream/call-live-101") as websocket:
        # 1. Connection ACK
        ack = websocket.receive_json()
        assert ack["type"] == "CONNECTION_ACK"
        assert ack["call_id"] == "call-live-101"
        assert ack["status"] == "STREAMING_READY"

        # 2. Ping / Pong
        websocket.send_json({"type": "PING"})
        pong = websocket.receive_json()
        assert pong["type"] == "PONG"

        # 3. Send Chunk 1 (Recording disclosure)
        websocket.send_json({
            "type": "TRANSCRIPT_CHUNK",
            "speaker": "AGENT",
            "text": "Hi this is Alex, please note this call is recorded for quality assurance.",
            "timestamp_ms": 1000
        })
        eval1 = websocket.receive_json()
        assert eval1["type"] == "INCREMENTAL_EVALUATION"
        assert eval1["live_checks"]["recording_disclosure"] == "PASS"
        assert eval1["live_checks"]["explicit_informed_consent"] == "PENDING"

        # 4. Send Chunk 2 (Explicit Informed Consent)
        websocket.send_json({
            "type": "TRANSCRIPT_CHUNK",
            "speaker": "AGENT",
            "text": "Do you give your explicit informed consent to switch to our market offer?",
            "timestamp_ms": 5000
        })
        eval2 = websocket.receive_json()
        assert eval2["type"] == "INCREMENTAL_EVALUATION"
        assert eval2["live_checks"]["recording_disclosure"] == "PASS"
        assert eval2["live_checks"]["explicit_informed_consent"] == "PASS"

        # 5. Send STREAM_END
        websocket.send_json({"type": "STREAM_END"})
        end_msg = websocket.receive_json()
        assert end_msg["type"] == "STREAM_COMPLETED"
        assert end_msg["total_chunks"] == 2
        assert end_msg["final_status"] == "QUEUED_FOR_FULL_AUDIT"
