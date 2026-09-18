"""Tests for immutable Artifact entity and SHA-256 content hashing."""

from dataclasses import FrozenInstanceError

import pytest

from packages.domain.artifacts import Artifact


def test_artifact_content_hashing_invariant():
    """Identical bytes must produce identical hashes; different bytes must produce different hashes."""
    data_1 = b"audio-sample-data-lead-3613790"
    data_2 = b"audio-sample-data-lead-3613790"
    data_diff = b"different-audio-bytes"

    art1 = Artifact.create("lead-1", "recordings/1.wav", data_1, "audio/wav")
    art2 = Artifact.create("lead-2", "recordings/2.wav", data_2, "audio/wav")
    art_diff = Artifact.create("lead-3", "recordings/3.wav", data_diff, "audio/wav")

    # Invariant 1: Deterministic SHA-256 matching
    assert art1.content_hash == art2.content_hash
    assert art1.content_hash != art_diff.content_hash
    assert len(art1.content_hash) == 64  # SHA-256 hex length
    assert art1.size_bytes == len(data_1)


def test_artifact_immutability_enforced():
    """Attempting to mutate any field of an Artifact must be rejected."""
    art = Artifact.create("lead-1", "recordings/1.wav", b"raw-audio", "audio/wav")

    with pytest.raises(FrozenInstanceError):
        art.content_hash = "hacked-hash"  # type: ignore

    with pytest.raises(FrozenInstanceError):
        art.size_bytes = 999999  # type: ignore

    with pytest.raises(FrozenInstanceError):
        art.storage_key = "new/path.wav"  # type: ignore
