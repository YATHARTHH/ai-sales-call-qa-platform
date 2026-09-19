"""Canonical serializer and SHA-256 content hasher for evaluation input snapshots."""

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from packages.domain.evaluation import EvaluationInputSnapshot


def _normalize_value(val: Any) -> Any:
    """Recursively normalizes data structures for canonical JSON serialization.

    Strictly rejects sets and unordered collections to ensure deterministic hashing.
    """
    if isinstance(val, (set, frozenset)):
        raise TypeError(
            f"Sets and unordered collections ({type(val).__name__}) are strictly prohibited "
            "in canonical snapshot serialization."
        )

    if isinstance(val, Enum):
        return val.value

    if isinstance(val, Decimal):
        return str(val)

    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=UTC)
        return val.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    if is_dataclass(val) and not isinstance(val, type):
        return _normalize_value(asdict(val))

    if isinstance(val, dict):
        return {str(k): _normalize_value(v) for k, v in sorted(val.items(), key=lambda x: str(x[0]))}

    if isinstance(val, (list, tuple)):
        return [_normalize_value(item) for item in val]

    return val


def serialize_canonical_json(obj: Any) -> str:
    """Serialize any normalized Python object into bit-for-bit reproducible canonical JSON.

    - Keys are lexicographically sorted.
    - Separators have no insignificant whitespace (',', ':').
    - UTF-8 compatible formatting.
    - Strict rejection of unordered types (sets).
    """
    normalized = _normalize_value(obj)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def extract_snapshot_content_dict(snapshot: EvaluationInputSnapshot | dict[str, Any]) -> dict[str, Any]:
    """Extract strictly content-bearing fields from an evaluation snapshot.

    Excludes record-level metadata (snapshot_id, created_at, created_by, snapshot_content_hash)
    so reruns with identical factual inputs yield bit-for-bit identical hashes.
    """
    if isinstance(snapshot, EvaluationInputSnapshot):
        return {
            "snapshot_schema_version": snapshot.snapshot_schema_version,
            "sale_snapshot": snapshot.sale_snapshot,
            "lead_snapshot": snapshot.lead_snapshot,
            "transcript_version_id": snapshot.transcript_version_id,
            "transcript_content_hash": snapshot.transcript_content_hash,
            "audio_artifact_hash": snapshot.audio_artifact_hash,
            "resolved_check_snapshots": list(snapshot.resolved_check_snapshots),
            "policy_version": snapshot.policy_version,
            "evaluator_config_hash": snapshot.evaluator_config_hash,
            "applicability_version": snapshot.applicability_version,
        }

    return {
        "snapshot_schema_version": snapshot.get("snapshot_schema_version", "snapshot.v1"),
        "sale_snapshot": snapshot.get("sale_snapshot", {}),
        "lead_snapshot": snapshot.get("lead_snapshot", {}),
        "transcript_version_id": snapshot.get("transcript_version_id", ""),
        "transcript_content_hash": snapshot.get("transcript_content_hash", ""),
        "audio_artifact_hash": snapshot.get("audio_artifact_hash", ""),
        "resolved_check_snapshots": list(snapshot.get("resolved_check_snapshots", [])),
        "policy_version": snapshot.get("policy_version", ""),
        "evaluator_config_hash": snapshot.get("evaluator_config_hash", ""),
        "applicability_version": snapshot.get("applicability_version", "v1"),
    }


def compute_snapshot_content_hash(snapshot: EvaluationInputSnapshot | dict[str, Any]) -> str:
    """Computes SHA-256 hexadecimal hash over the canonical JSON of evaluation content inputs."""
    content_dict = extract_snapshot_content_dict(snapshot)
    canonical_str = serialize_canonical_json(content_dict)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


def create_evaluation_input_snapshot(
    sale_id: str,
    tenant_id: str,
    transcript_id: str,
    transcript_version_id: str,
    transcript_content_hash: str,
    audio_artifact_hash: str,
    sale_snapshot: dict[str, Any],
    lead_snapshot: dict[str, Any],
    resolved_check_snapshots: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    policy_version: str,
    evaluator_config_hash: str,
    applicability_version: str = "v1",
    snapshot_id: str | None = None,
    created_by: str = "system:worker",
) -> EvaluationInputSnapshot:
    """Builds a frozen EvaluationInputSnapshot with its canonical snapshot_content_hash populated."""
    # First instantiate without content hash
    prelim = EvaluationInputSnapshot.create(
        sale_id=sale_id,
        tenant_id=tenant_id,
        transcript_id=transcript_id,
        transcript_version_id=transcript_version_id,
        transcript_content_hash=transcript_content_hash,
        audio_artifact_hash=audio_artifact_hash,
        sale_snapshot=sale_snapshot,
        lead_snapshot=lead_snapshot,
        resolved_check_snapshots=resolved_check_snapshots,
        policy_version=policy_version,
        evaluator_config_hash=evaluator_config_hash,
        applicability_version=applicability_version,
        snapshot_id=snapshot_id,
        created_by=created_by,
    )

    # Compute content hash strictly over content fields
    computed_hash = compute_snapshot_content_hash(prelim)

    # Return final immutable snapshot with content hash set
    return EvaluationInputSnapshot(
        snapshot_id=prelim.snapshot_id,
        sale_id=prelim.sale_id,
        tenant_id=prelim.tenant_id,
        transcript_id=prelim.transcript_id,
        transcript_version_id=prelim.transcript_version_id,
        transcript_content_hash=prelim.transcript_content_hash,
        audio_artifact_hash=prelim.audio_artifact_hash,
        sale_snapshot=prelim.sale_snapshot,
        lead_snapshot=prelim.lead_snapshot,
        resolved_check_snapshots=prelim.resolved_check_snapshots,
        policy_version=prelim.policy_version,
        evaluator_config_hash=prelim.evaluator_config_hash,
        applicability_version=prelim.applicability_version,
        snapshot_schema_version=prelim.snapshot_schema_version,
        created_by=prelim.created_by,
        snapshot_content_hash_algorithm=prelim.snapshot_content_hash_algorithm,
        snapshot_content_hash=computed_hash,
        created_at=prelim.created_at,
    )
