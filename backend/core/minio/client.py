import logging
from minio import Minio
from urllib3 import PoolManager, Timeout
from core.config.settings import settings

logger = logging.getLogger(__name__)

# Short timeout so startup doesn't hang if MinIO is unavailable
_http = PoolManager(
    timeout=Timeout(connect=2.0, read=5.0),
    retries=False,
)

try:
    minio_client = Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=False,
        http_client=_http,
    )
except Exception as e:
    logger.warning("MinIO client init failed (will retry): %s", e)
    minio_client = None


async def ensure_buckets():
    if minio_client is None:
        logger.warning("MinIO not available, skipping bucket setup")
        return
    try:
        buckets = ["user-files", "music", "videos", "documents", "thumbnails", "backups"]
        for bucket in buckets:
            if not minio_client.bucket_exists(bucket):
                minio_client.make_bucket(bucket)
    except Exception as e:
        logger.warning("MinIO unavailable (non-fatal): %s", e)
