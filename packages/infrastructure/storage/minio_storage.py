"""MinIO S3 storage adapter implementing StoragePort."""

import asyncio

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from packages.application.ports.storage import StoragePort
from packages.infrastructure.config.settings import settings


class MinioStorageAdapter(StoragePort):
    """S3-compatible object storage adapter for local MinIO."""

    def __init__(self) -> None:
        self.endpoint_url = f"{'https' if settings.minio_secure else 'http'}://{settings.minio_endpoint}"
        self.access_key = settings.minio_access_key
        self.secret_key = settings.minio_secret_key

    def _get_client(self):
        return boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(signature_version="s3v4"),
        )

    async def upload_object(
        self, bucket: str, key: str, data: bytes, content_type: str
    ) -> None:
        """Upload binary object data asynchronously."""
        def _upload() -> None:
            client = self._get_client()
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )

        await asyncio.to_thread(_upload)

    async def download_object(self, bucket: str, key: str) -> bytes:
        """Download binary object data asynchronously."""
        def _download() -> bytes:
            client = self._get_client()
            response = client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()

        return await asyncio.to_thread(_download)

    async def bucket_exists(self, bucket: str) -> bool:
        """Verify bucket existence."""
        def _exists() -> bool:
            client = self._get_client()
            try:
                client.head_bucket(Bucket=bucket)
                return True
            except ClientError:
                return False

        return await asyncio.to_thread(_exists)

    async def check_connection(self) -> bool:
        """Probe MinIO connectivity."""
        def _check() -> bool:
            try:
                client = self._get_client()
                client.list_buckets()
                return True
            except Exception:
                return False

        return await asyncio.to_thread(_check)
