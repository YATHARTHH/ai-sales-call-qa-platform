"""Storage port contract for object storage operations."""

from abc import ABC, abstractmethod


class StoragePort(ABC):
    """Abstract interface for S3/MinIO object storage operations."""

    @abstractmethod
    async def upload_object(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        """Upload binary object data to the target bucket."""

    async def upload_file(self, bucket: str, key: str, file_path: str, content_type: str) -> None:
        """Upload a file from disk to object storage with bounded memory."""
        with open(file_path, "rb") as f:
            data = f.read()
        await self.upload_object(bucket, key, data, content_type)

    @abstractmethod
    async def download_object(self, bucket: str, key: str) -> bytes:
        """Download binary object data from the target bucket."""

    @abstractmethod
    async def bucket_exists(self, bucket: str) -> bool:
        """Check if a bucket exists in object storage."""

    @abstractmethod
    async def object_exists(self, bucket: str, key: str) -> bool:
        """Check if an object exists in the target bucket."""

    @abstractmethod
    async def delete_object(self, bucket: str, key: str) -> None:
        """Delete an object from the target bucket."""

    @abstractmethod
    async def get_presigned_url(self, bucket: str, key: str, expires_in_seconds: int = 3600) -> str:
        """Generate a presigned GET URL for direct client playback/download."""

    @abstractmethod
    async def check_connection(self) -> bool:
        """Verify storage engine readiness."""
