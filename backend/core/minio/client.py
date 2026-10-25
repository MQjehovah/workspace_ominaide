import logging
from urllib.parse import urlsplit, urlunsplit

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


def public_minio_url(url: str) -> str:
    """Rewrite an internal presigned MinIO URL to the public reverse-proxy path.

    The presigned signature is bound to Host ``minio:9000`` and the bare object
    path. nginx exposes it as ``https://mqgeek.com/minio/<bucket>/<key>``, sets
    ``Host: minio:9000`` and strips ``/minio`` before proxying to MinIO, so the
    signature still validates.
    """
    base = (settings.minio_public_url or "").strip().rstrip("/")
    if not base or not url:
        return url
    try:
        src = urlsplit(url)
        pub = urlsplit(base)
        path = f"{pub.path.rstrip('/')}{src.path}"
        return urlunsplit((pub.scheme or src.scheme, pub.netloc, path, src.query, src.fragment))
    except Exception:
        return url


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
