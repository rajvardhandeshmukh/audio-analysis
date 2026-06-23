"""MinIO object storage provider — implements StorageProvider port."""

import io
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error

from src.domain.errors.domain_errors import (
    FileNotFoundInStorageError,
    StorageUploadError,
)
from src.domain.ports.storage_messaging import StorageProvider
from src.infrastructure.config.settings import StorageSettings, get_storage_settings
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class MinioStorageProvider(StorageProvider):
    """S3-compatible object storage via MinIO SDK.

    Rule 5: Only this class calls the minio SDK.
    """

    def __init__(self, client: Minio, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @classmethod
    def from_settings(cls, settings: StorageSettings | None = None) -> "MinioStorageProvider":
        cfg = settings or get_storage_settings()
        client = Minio(
            cfg.minio_endpoint,
            access_key=cfg.minio_access_key,
            secret_key=cfg.minio_secret_key,
            secure=cfg.minio_secure,
        )
        instance = cls(client, cfg.minio_bucket)
        instance._ensure_bucket()
        return instance

    def _ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)
            logger.info("storage.bucket_created", bucket=self._bucket)

    async def upload(self, local_path: str, storage_key: str) -> str:
        """Upload a local file to object storage.

        Args:
            local_path: Absolute path to the local file.
            storage_key: Destination key within the bucket.

        Returns:
            The storage_key confirming the upload path.

        Raises:
            StorageUploadError: On S3 failure.
        """
        try:
            self._client.fput_object(self._bucket, storage_key, local_path)
            logger.info("storage.uploaded", key=storage_key, bucket=self._bucket)
            return storage_key
        except S3Error as exc:
            raise StorageUploadError(f"Upload failed for '{storage_key}': {exc}") from exc

    async def download(self, storage_key: str, local_path: str) -> None:
        """Download a file from object storage to a local path.

        Args:
            storage_key: Source key within the bucket.
            local_path: Destination local path.

        Raises:
            FileNotFoundInStorageError: If the key does not exist.
            StorageError: On other S3 failures.
        """
        try:
            self._client.fget_object(self._bucket, storage_key, local_path)
            logger.info("storage.downloaded", key=storage_key)
        except S3Error as exc:
            if exc.code == "NoSuchKey":
                raise FileNotFoundInStorageError(
                    f"Object '{storage_key}' not found in bucket '{self._bucket}'."
                ) from exc
            raise

    async def generate_presigned_url(self, storage_key: str, expires_in_seconds: int = 3600) -> str:
        """Generate a time-limited presigned download URL.

        Args:
            storage_key: Object key in the bucket.
            expires_in_seconds: URL validity duration in seconds.

        Returns:
            Presigned HTTPS URL string.
        """
        from datetime import timedelta
        url = self._client.presigned_get_object(
            self._bucket, storage_key, expires=timedelta(seconds=expires_in_seconds)
        )
        return url

    async def delete(self, storage_key: str) -> None:
        """Delete an object from storage.

        Args:
            storage_key: Object key to remove.
        """
        try:
            self._client.remove_object(self._bucket, storage_key)
            logger.info("storage.deleted", key=storage_key)
        except S3Error as exc:
            logger.warning("storage.delete_failed", key=storage_key, error=str(exc))

    async def exists(self, storage_key: str) -> bool:
        """Check if an object exists in storage."""
        try:
            self._client.stat_object(self._bucket, storage_key)
            return True
        except S3Error as exc:
            if exc.code in ("NoSuchKey", "NoSuchObject"):
                return False
            raise
