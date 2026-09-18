"""MinIO S3 storage adapter implementing StoragePort."""

import asyncio
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from packages.application.ports.storage import StoragePort
from packages.infrastructure.config.settings import settings


class MinioStorageAdapter(StoragePort):
    """S3-compatible object storage adapter for MinIO."""

    def __init__(self) -> None:
        scheme = "https" if settings.minio_secure else "http"
        self.internal_endpoint_url = f"{scheme}://{settings.minio_endpoint}"
        self.public_endpoint_url = f"{scheme}://{settings.minio_public_endpoint}"
        self.access_key = settings.minio_access_key
        self.secret_key = settings.minio_secret_key

    def _get_internal_client(self) -> Any:
        return boto3.client(
            "s3",
            endpoint_url=self.internal_endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(signature_version="s3v4"),
        )

    def _get_public_client(self) -> Any:
        return boto3.client(
            "s3",
            endpoint_url=self.public_endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(signature_version="s3v4"),
        )

    async def upload_object(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        """Upload binary object data asynchronously."""

        def _upload() -> None:
            client = self._get_internal_client()
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )

        await asyncio.to_thread(_upload)

    async def upload_file(self, bucket: str, key: str, file_path: str, content_type: str) -> None:
        """Upload a local file path to storage without reading full file into memory."""

        def _upload() -> None:
            client = self._get_internal_client()
            client.upload_file(
                Filename=file_path,
                Bucket=bucket,
                Key=key,
                ExtraArgs={"ContentType": content_type},
            )

        await asyncio.to_thread(_upload)

    async def download_object(self, bucket: str, key: str) -> bytes:
        """Download binary object data asynchronously."""

        def _download() -> bytes:
            client = self._get_internal_client()
            response = client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()

        return await asyncio.to_thread(_download)

    async def bucket_exists(self, bucket: str) -> bool:
        """Verify bucket existence."""

        def _exists() -> bool:
            client = self._get_internal_client()
            try:
                client.head_bucket(Bucket=bucket)
                return True
            except ClientError:
                return False

        return await asyncio.to_thread(_exists)

    async def object_exists(self, bucket: str, key: str) -> bool:
        """Check if an object exists in storage."""

        def _check() -> bool:
            client = self._get_internal_client()
            try:
                client.head_object(Bucket=bucket, Key=key)
                return True
            except ClientError:
                return False

        return await asyncio.to_thread(_check)

    async def delete_object(self, bucket: str, key: str) -> None:
        """Delete an object from storage."""

        def _delete() -> None:
            client = self._get_internal_client()
            try:
                client.delete_object(Bucket=bucket, Key=key)
            except ClientError:
                pass

        await asyncio.to_thread(_delete)

    async def get_presigned_url(self, bucket: str, key: str, expires_in_seconds: int = 3600) -> str:
        """Generate a presigned download URL for direct client playback."""

        def _sign() -> str:
            client = self._get_public_client()
            return client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires_in_seconds,
            )

        return await asyncio.to_thread(_sign)

    async def check_connection(self) -> bool:
        """Probe MinIO connectivity."""

        def _check() -> bool:
            try:
                client = self._get_internal_client()
                client.list_buckets()
                return True
            except Exception:
                return False

        return await asyncio.to_thread(_check)
