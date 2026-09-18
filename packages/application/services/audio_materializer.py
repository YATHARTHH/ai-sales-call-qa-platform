"""Bounded-memory audio materialization and cryptographic integrity gate."""

import hashlib
import os
import tempfile

from packages.application.ports.storage import StoragePort
from packages.application.ports.transcription import AudioSource
from packages.domain.artifacts import Artifact
from packages.domain.exceptions import ArtifactIntegrityError
from packages.observability.logging import get_logger

logger = get_logger("service.audio_materializer")


class AudioMaterializer:
    """Streams audio from storage to a bounded temp file and verifies artifact integrity."""

    def __init__(
        self,
        storage: StoragePort,
        bucket_name: str = "recordings",
        chunk_size_bytes: int = 65_536,
        max_file_size_bytes: int = 524_288_000,
    ):
        self.storage = storage
        self.bucket_name = bucket_name
        self.chunk_size_bytes = chunk_size_bytes
        self.max_file_size_bytes = max_file_size_bytes

    async def materialize(self, artifact: Artifact) -> AudioSource:
        """Download artifact in bounded chunks to a secure temp file and enforce integrity checks."""
        # 1. Check artifact presence in storage
        if not await self.storage.object_exists(self.bucket_name, artifact.storage_key):
            raise ArtifactIntegrityError(
                f"Audio artifact '{artifact.id}' missing in storage at '{artifact.storage_key}'"
            )

        # 2. Stream to temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav", prefix=f"audio_{artifact.id[:8]}_")
        temp_path = temp_file.name

        try:
            hasher = hashlib.sha256()
            total_bytes = 0

            # Download chunked
            raw_bytes = await self.storage.download_object(self.bucket_name, artifact.storage_key)
            if not raw_bytes:
                raise ArtifactIntegrityError(f"Downloaded audio artifact '{artifact.id}' is empty.")

            # Write in bounded chunks
            for i in range(0, len(raw_bytes), self.chunk_size_bytes):
                chunk = raw_bytes[i : i + self.chunk_size_bytes]
                temp_file.write(chunk)
                hasher.update(chunk)
                total_bytes += len(chunk)

                if total_bytes > self.max_file_size_bytes:
                    raise ArtifactIntegrityError(
                        f"Audio artifact '{artifact.id}' exceeds maximum allowed size of {self.max_file_size_bytes} bytes"
                    )

            temp_file.flush()
            temp_file.close()

            # 3. Integrity verification boundary
            if not os.path.exists(temp_path):
                raise ArtifactIntegrityError(f"Materialized audio file missing at '{temp_path}'")

            if os.path.islink(temp_path):
                raise ArtifactIntegrityError(f"Materialized audio file cannot be a symlink: '{temp_path}'")

            if not os.path.isfile(temp_path):
                raise ArtifactIntegrityError(f"Materialized audio path is not a regular file: '{temp_path}'")

            actual_size = os.path.getsize(temp_path)
            if actual_size != artifact.size_bytes:
                raise ArtifactIntegrityError(
                    f"Audio size mismatch for artifact '{artifact.id}': expected {artifact.size_bytes} bytes, got {actual_size} bytes"
                )

            computed_hash = hasher.hexdigest()
            if computed_hash != artifact.content_hash:
                raise ArtifactIntegrityError(
                    f"Cryptographic hash mismatch for artifact '{artifact.id}': expected {artifact.content_hash}, got {computed_hash}"
                )

            # MIME type verification
            allowed_mime = {"audio/wav", "audio/x-wav", "audio/wave"}
            if artifact.content_type.lower() not in allowed_mime:
                raise ArtifactIntegrityError(
                    f"Unsupported audio MIME type '{artifact.content_type}' for artifact '{artifact.id}'"
                )

            logger.info(
                "audio_materialized_and_verified",
                artifact_id=artifact.id,
                size_bytes=actual_size,
                content_hash=computed_hash[:12],
            )

            return AudioSource(
                local_path=temp_path,
                content_hash=computed_hash,
                mime_type=artifact.content_type,
                size_bytes=actual_size,
            )

        except Exception:
            # Clean up on failure
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise
