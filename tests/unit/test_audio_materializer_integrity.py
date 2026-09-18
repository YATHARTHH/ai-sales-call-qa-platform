"""Unit tests for bounded audio materialization and cryptographic integrity gates."""

import hashlib
import os
from datetime import UTC, datetime

import pytest

from packages.application.ports.storage import StoragePort
from packages.application.services.audio_materializer import AudioMaterializer
from packages.domain.artifacts import Artifact
from packages.domain.exceptions import ArtifactIntegrityError


class MockStorageAdapter(StoragePort):
    def __init__(self):
        self.objects = {}

    async def upload_object(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        self.objects[f"{bucket}/{key}"] = data

    async def upload_file(self, bucket: str, key: str, file_path: str, content_type: str) -> None:
        with open(file_path, "rb") as f:
            self.objects[f"{bucket}/{key}"] = f.read()

    async def download_object(self, bucket: str, key: str) -> bytes:
        return self.objects.get(f"{bucket}/{key}", b"")

    async def object_exists(self, bucket: str, key: str) -> bool:
        return f"{bucket}/{key}" in self.objects

    async def bucket_exists(self, bucket: str) -> bool:
        return True

    async def delete_object(self, bucket: str, key: str) -> None:
        self.objects.pop(f"{bucket}/{key}", None)

    async def check_connection(self) -> bool:
        return True

    async def get_presigned_url(self, bucket: str, key: str, expires_in_seconds: int = 3600) -> str:
        return f"https://mock/{bucket}/{key}"


@pytest.mark.asyncio
async def test_materializer_succeeds_for_valid_artifact():
    """Valid audio data downloads and verifies successfully, returning AudioSource."""
    storage = MockStorageAdapter()
    raw_audio = b"RIFF" + b"\x00" * 1000  # mock wav header
    content_hash = hashlib.sha256(raw_audio).hexdigest()

    await storage.upload_object("recordings", "audio/rec1.wav", raw_audio, "audio/wav")

    art = Artifact(
        id="art-1",
        lead_id="lead-1",
        storage_key="audio/rec1.wav",
        content_hash=content_hash,
        content_type="audio/wav",
        size_bytes=len(raw_audio),
        created_at=datetime.now(UTC),
    )

    materializer = AudioMaterializer(storage=storage, bucket_name="recordings")
    source = await materializer.materialize(art)

    try:
        assert os.path.exists(source.local_path)
        assert not os.path.islink(source.local_path)
        assert os.path.isfile(source.local_path)
        assert source.size_bytes == len(raw_audio)
        assert source.content_hash == content_hash
        assert source.mime_type == "audio/wav"
    finally:
        if os.path.exists(source.local_path):
            os.remove(source.local_path)


@pytest.mark.asyncio
async def test_materializer_rejects_hash_mismatch():
    """If stored bytes do not match artifact content_hash, raises ArtifactIntegrityError."""
    storage = MockStorageAdapter()
    raw_audio = b"corrupted-audio-data"
    expected_hash = "0000000000000000000000000000000000000000000000000000000000000000"

    await storage.upload_object("recordings", "audio/bad_hash.wav", raw_audio, "audio/wav")

    art = Artifact(
        id="art-bad-hash",
        lead_id="lead-1",
        storage_key="audio/bad_hash.wav",
        content_hash=expected_hash,
        content_type="audio/wav",
        size_bytes=len(raw_audio),
        created_at=datetime.now(UTC),
    )

    materializer = AudioMaterializer(storage=storage, bucket_name="recordings")
    with pytest.raises(ArtifactIntegrityError) as exc_info:
        await materializer.materialize(art)

    assert "Cryptographic hash mismatch" in exc_info.value.message


@pytest.mark.asyncio
async def test_materializer_rejects_size_mismatch():
    """If stored size does not match artifact metadata size_bytes, raises ArtifactIntegrityError."""
    storage = MockStorageAdapter()
    raw_audio = b"short-audio"

    await storage.upload_object("recordings", "audio/bad_size.wav", raw_audio, "audio/wav")

    art = Artifact(
        id="art-bad-size",
        lead_id="lead-1",
        storage_key="audio/bad_size.wav",
        content_hash=hashlib.sha256(raw_audio).hexdigest(),
        content_type="audio/wav",
        size_bytes=999999,  # Mismatched size
        created_at=datetime.now(UTC),
    )

    materializer = AudioMaterializer(storage=storage, bucket_name="recordings")
    with pytest.raises(ArtifactIntegrityError) as exc_info:
        await materializer.materialize(art)

    assert "Audio size mismatch" in exc_info.value.message


@pytest.mark.asyncio
async def test_materializer_rejects_unsupported_mime():
    """Non-WAV MIME types raise ArtifactIntegrityError."""
    storage = MockStorageAdapter()
    raw_audio = b"mp3-data"

    await storage.upload_object("recordings", "audio/music.mp3", raw_audio, "audio/mp3")

    art = Artifact(
        id="art-bad-mime",
        lead_id="lead-1",
        storage_key="audio/music.mp3",
        content_hash=hashlib.sha256(raw_audio).hexdigest(),
        content_type="audio/mp3",
        size_bytes=len(raw_audio),
        created_at=datetime.now(UTC),
    )

    materializer = AudioMaterializer(storage=storage, bucket_name="recordings")
    with pytest.raises(ArtifactIntegrityError) as exc_info:
        await materializer.materialize(art)

    assert "Unsupported audio MIME type" in exc_info.value.message
