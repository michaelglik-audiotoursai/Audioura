"""
BlobStorage Abstraction Layer for Audioura Services
====================================================

Provides a unified interface for storing/retrieving tour ZIP files.
Implementations:
  - DatabaseBlobStorage: reads/writes BYTEA in audio_tours (current behavior)
  - R2BlobStorage: reads/writes to Cloudflare R2 via S3 API (Phase D)

Feature flag: BLOB_STORAGE_TYPE env var
  - 'database' (default): current behavior, stores in PostgreSQL BYTEA
  - 'r2': stores in Cloudflare R2, stores URI in audio_tours.tour_blob_uri

Local dev: BLOB_STORAGE_TYPE=database (unchanged from today)
Cloud Run: BLOB_STORAGE_TYPE=r2 (after Phase D migration)
"""

import os
import logging

logger = logging.getLogger(__name__)


class BlobStorage:
    """Abstract interface for tour/news ZIP storage."""

    def upload(self, key: str, data: bytes) -> str:
        """Upload binary data. Returns the storage URI/key."""
        raise NotImplementedError

    def download(self, key: str) -> bytes:
        """Download binary data by key. Returns bytes."""
        raise NotImplementedError

    def delete(self, key: str) -> None:
        """Delete binary data by key."""
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        """Check if key exists in storage."""
        raise NotImplementedError

    def health_check(self) -> bool:
        """Return True if storage backend is reachable."""
        raise NotImplementedError


class R2BlobStorage(BlobStorage):
    """Cloudflare R2 storage backend (S3-compatible)."""

    def __init__(self, endpoint=None, access_key=None, secret_key=None, bucket=None):
        import boto3
        from botocore.config import Config
        from urllib.parse import urlparse
        self.bucket = bucket or os.getenv('R2_BUCKET', 'v1-audiotours-r2-bucket')
        access = access_key or os.getenv('R2_ACCESS_KEY_ID', '')
        secret = secret_key or os.getenv('R2_SECRET_ACCESS_KEY', '')
        
        # R2 endpoint must be base URL only (no bucket path)
        raw_endpoint = endpoint or os.getenv('R2_ENDPOINT', '')
        parsed = urlparse(raw_endpoint)
        self.endpoint = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else raw_endpoint

        self.client = boto3.client(
            's3',
            endpoint_url=self.endpoint,
            aws_access_key_id=access,
            aws_secret_access_key=secret,
            region_name='auto',
            config=Config(
                retries={'max_attempts': 3, 'mode': 'standard'},
                connect_timeout=10,
                read_timeout=30
            )
        )
        logger.info(f"R2BlobStorage initialized: bucket={self.bucket}, endpoint={self.endpoint}")

    def upload(self, key: str, data: bytes) -> str:
        """Upload to R2. Key format: 'tours/{tour_id}.zip' or 'news/{article_id}.zip'
        Returns the bare key (same value stored in tour_blob_uri/news_blob_uri)."""
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        logger.info(f"R2 upload: {key} ({len(data)} bytes)")
        return key

    def download(self, key: str) -> bytes:
        """Download from R2."""
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        data = response['Body'].read()
        logger.info(f"R2 download: {key} ({len(data)} bytes)")
        return data

    def delete(self, key: str) -> None:
        """Delete from R2."""
        self.client.delete_object(Bucket=self.bucket, Key=key)
        logger.info(f"R2 delete: {key}")

    def exists(self, key: str) -> bool:
        """Check if object exists in R2."""
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except self.client.exceptions.ClientError:
            return False

    def health_check(self) -> bool:
        """Check R2 connectivity by listing bucket (zero-cost HEAD)."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True
        except Exception as e:
            logger.error(f"R2 health check failed: {e}")
            return False


class DatabaseBlobStorage(BlobStorage):
    """
    PostgreSQL BYTEA storage backend (current behavior).
    This is a passthrough — the actual DB read/write happens in the service code.
    This class exists so services can use a unified interface regardless of backend.
    """

    def __init__(self):
        logger.info("DatabaseBlobStorage initialized (passthrough mode)")

    def upload(self, key: str, data: bytes) -> str:
        """
        In database mode, the service code handles the INSERT/UPDATE directly.
        This returns a marker URI indicating database storage.
        """
        return f"db://audio_tours/{key}"

    def download(self, key: str) -> bytes:
        """
        In database mode, the service code handles the SELECT directly.
        This should not be called — services read BYTEA directly.
        """
        raise NotImplementedError(
            "DatabaseBlobStorage.download() should not be called. "
            "Services read BYTEA directly from PostgreSQL."
        )

    def delete(self, key: str) -> None:
        """In database mode, deletion is handled by SQL DELETE."""
        pass

    def exists(self, key: str) -> bool:
        """In database mode, existence is checked via SQL SELECT."""
        return True  # Assume exists; actual check is in service code

    def health_check(self) -> bool:
        """Database health is checked separately via DB connection."""
        return True


def get_blob_storage() -> BlobStorage:
    """
    Factory function. Returns the appropriate BlobStorage implementation
    based on the BLOB_STORAGE_TYPE environment variable.

    BLOB_STORAGE_TYPE:
      'database' (default) - current behavior, services handle BYTEA directly
      'r2' - Cloudflare R2 via S3 API
    """
    storage_type = os.getenv('BLOB_STORAGE_TYPE', 'database')

    if storage_type == 'r2':
        return R2BlobStorage()
    else:
        return DatabaseBlobStorage()
