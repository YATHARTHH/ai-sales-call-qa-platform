"""Tests for stage-specific idempotency key generation."""

from packages.domain.jobs import PipelineJob


def test_stage_specific_idempotency_key():
    """Key format must include recording_id, stage, input_artifact_hash, and processor_version."""
    rec_id = "rec-3613790"
    stage = "transcription"
    hash_v1 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    proc_v1 = "whisper-large-v3"
    proc_v2 = "deepgram-nova-2"

    key1 = PipelineJob.build_idempotency_key(rec_id, stage, hash_v1, proc_v1)
    key2 = PipelineJob.build_idempotency_key(rec_id, stage, hash_v1, proc_v1)
    key_new_model = PipelineJob.build_idempotency_key(rec_id, stage, hash_v1, proc_v2)

    # Same inputs must produce exact same idempotency key
    assert key1 == key2
    assert key1 == f"{rec_id}:{stage}:{hash_v1}:{proc_v1}"

    # New processor version produces distinct key for reprocessing
    assert key1 != key_new_model
