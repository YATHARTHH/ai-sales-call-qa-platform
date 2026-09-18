"""Storage port contract for object storage operations."""

from abc import ABC, abstractmethod


class StoragePort(ABC):
    """Abstract interface for S3/MinIO object storage operations."""

    @abstractmethod
    async def upload_object(
        self, bucket: str, key: str, data: bytes, content_type: str
    ) -> None:
        """Upload binary object data to the target bucket."""

    @abstractmethod
    async def download_object(self, bucket: str, key: str) -> bytes:
        """Download binary object data from the target bucket."""

    @abstractmethod
    async def bucket_exists(self, bucket: str) -> bool:
        """Check if a bucket exists in object storage."""

    @abstractmethod
    async def check_connection(self) -> bool:
        """Verify storage engine readiness."""
