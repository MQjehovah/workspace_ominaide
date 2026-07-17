from minio import Minio
from core.config.settings import settings

minio_client = Minio(
    endpoint=settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=False,
)


async def ensure_buckets():
    buckets = ["user-files", "music", "videos", "documents", "thumbnails", "backups"]
    for bucket in buckets:
        if not minio_client.bucket_exists(bucket):
            minio_client.make_bucket(bucket)
