"""Unit tests for canonical snapshot serializer and content hashing."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from packages.application.services.snapshot_serializer import (
    compute_snapshot_content_hash,
    create_evaluation_input_snapshot,
    serialize_canonical_json,
)


def test_serialize_canonical_json_formatting():
    data = {
        "z_key": Decimal("31.90"),
        "a_key": "test",
        "time": datetime(2026, 9, 19, 10, 0, 0, tzinfo=UTC),
        "nested": {"b": 2, "a": 1},
        "items": [3, 2, 1],
    }
    canonical = serialize_canonical_json(data)
    expected = (
        '{"a_key":"test","items":[3,2,1],"nested":{"a":1,"b":2},'
        '"time":"2026-09-19T10:00:00Z","z_key":"31.90"}'
    )
    assert canonical == expected


def test_serialize_canonical_json_rejects_sets():
    with pytest.raises(TypeError, match="Sets and unordered collections"):
        serialize_canonical_json({"invalid": {1, 2, 3}})

    with pytest.raises(TypeError, match="Sets and unordered collections"):
        serialize_canonical_json({"invalid": frozenset([1, 2])})


def test_snapshot_content_hash_invariance_to_record_metadata():
    sale = {"sale_id": "sale-100", "fuel_type": "ELECTRICITY"}
    lead = {"lead_id": "lead-100", "state": "VIC"}
    checks = [{"check_id": "chk-1", "code": "RATE_CHECK"}]

    snapshot_1 = create_evaluation_input_snapshot(
        sale_id="sale-100",
        tenant_id="tenant-a",
        transcript_id="tx-100",
        transcript_version_id="tx-ver-1",
        transcript_content_hash="hash-tx-123",
        audio_artifact_hash="hash-audio-456",
        sale_snapshot=sale,
        lead_snapshot=lead,
        resolved_check_snapshots=checks,
        policy_version="policy.v1",
        evaluator_config_hash="eval-hash-789",
        snapshot_id="snapshot-uuid-1",
        created_by="worker-instance-1",
    )

    snapshot_2 = create_evaluation_input_snapshot(
        sale_id="sale-100",
        tenant_id="tenant-a",
        transcript_id="tx-100",
        transcript_version_id="tx-ver-1",
        transcript_content_hash="hash-tx-123",
        audio_artifact_hash="hash-audio-456",
        sale_snapshot=sale,
        lead_snapshot=lead,
        resolved_check_snapshots=checks,
        policy_version="policy.v1",
        evaluator_config_hash="eval-hash-789",
        snapshot_id="snapshot-uuid-2",  # Different ID
        created_by="worker-instance-2",  # Different creator
    )

    # Identical content yields identical content hash
    assert snapshot_1.snapshot_content_hash == snapshot_2.snapshot_content_hash
    assert len(snapshot_1.snapshot_content_hash) == 64

    # Modifying content alters the hash
    snapshot_diff = create_evaluation_input_snapshot(
        sale_id="sale-100",
        tenant_id="tenant-a",
        transcript_id="tx-100",
        transcript_version_id="tx-ver-1",
        transcript_content_hash="hash-tx-123",
        audio_artifact_hash="hash-audio-456",
        sale_snapshot={"sale_id": "sale-100", "fuel_type": "GAS"},  # Changed
        lead_snapshot=lead,
        resolved_check_snapshots=checks,
        policy_version="policy.v1",
        evaluator_config_hash="eval-hash-789",
        snapshot_id="snapshot-uuid-3",
    )
    assert snapshot_1.snapshot_content_hash != snapshot_diff.snapshot_content_hash
