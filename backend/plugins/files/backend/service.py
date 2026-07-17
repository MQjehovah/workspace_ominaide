import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from minio import Minio
from core.config.settings import settings
from core.minio.client import minio_client
from plugins.files.backend.models import File
from plugins.files.backend.schemas import UploadUrlRequest, FileQueryParams, CreateFolderRequest


DEFAULT_BUCKET = "user-files"
UPLOAD_URL_EXPIRY = 600
DOWNLOAD_URL_EXPIRY = 1800


def _generate_object_key(user_id: int, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    unique = uuid.uuid4().hex
    return f"{user_id}/{unique}{'.' + ext if ext else ''}"


async def create_folder(
    db: AsyncSession, user_id: int, req: CreateFolderRequest
) -> File:
    bucket = f"ws-{user_id}" if req.workspace_id else DEFAULT_BUCKET
    object_key = f"folder:{user_id}/{uuid.uuid4().hex}"

    folder = File(
        user_id=user_id,
        workspace_id=req.workspace_id,
        bucket=bucket,
        object_key=object_key,
        original_name=req.name,
        is_folder=True,
        folder_path=req.parent_path,
        mime_type="application/folder",
        status="active",
    )
    db.add(folder)
    await db.flush()
    await db.refresh(folder)
    return folder


async def generate_upload_url(
    db: AsyncSession, user_id: int, req: UploadUrlRequest
) -> tuple[str, int, str]:
    object_key = _generate_object_key(user_id, req.filename)
    bucket = req.bucket or DEFAULT_BUCKET

    file_record = File(
        user_id=user_id,
        bucket=bucket,
        object_key=object_key,
        original_name=req.filename,
        mime_type=req.mime_type or "application/octet-stream",
        workspace_id=req.workspace_id,
        folder_path=req.folder_path,
        status="uploading",
    )
    db.add(file_record)
    await db.flush()
    await db.refresh(file_record)

    if minio_client:
        upload_url = minio_client.presigned_put_object(
            bucket, object_key, expires=timedelta(seconds=UPLOAD_URL_EXPIRY)
        )
    else:
        upload_url = ""

    return upload_url, file_record.id, object_key


async def confirm_upload(db: AsyncSession, user_id: int, file_id: int) -> File:
    result = await db.execute(
        select(File).where(File.id == file_id, File.user_id == user_id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise ValueError("File not found")

    try:
        obj_info = minio_client.stat_object(file_record.bucket, file_record.object_key)
        file_record.size = obj_info.size
    except Exception:
        file_record.size = 0

    file_record.status = "active"
    await db.flush()
    await db.refresh(file_record)
    return file_record


async def get_files(
    db: AsyncSession, user_id: int, params: FileQueryParams
) -> tuple[list[File], int]:
    query = select(File).where(File.user_id == user_id)

    if params.status:
        query = query.where(File.status == params.status)
    if params.workspace_id is not None:
        query = query.where(File.workspace_id == params.workspace_id)
    if params.bucket:
        query = query.where(File.bucket == params.bucket)
    if params.mime_type:
        query = query.where(File.mime_type.like(f"{params.mime_type}%"))
    if params.favorite is not None:
        query = query.where(File.is_favorite == params.favorite)
    if params.folder_path is not None:
        query = query.where(File.folder_path == params.folder_path)
    if params.is_folder is not None:
        query = query.where(File.is_folder == params.is_folder)



    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (params.page - 1) * params.page_size
    query = query.order_by(File.updated_at.desc()).offset(offset).limit(params.page_size)

    result = await db.execute(query)
    files = list(result.scalars().all())

    return files, total


async def get_file(db: AsyncSession, user_id: int, file_id: int) -> File | None:
    result = await db.execute(
        select(File).where(File.id == file_id, File.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_download_url(file_record: File) -> str:
    if not minio_client:
        return ""
    return minio_client.presigned_get_object(
        file_record.bucket,
        file_record.object_key,
        expires=timedelta(seconds=DOWNLOAD_URL_EXPIRY),
    )


async def update_tags(
    db: AsyncSession, user_id: int, file_id: int, tags: list[str]
) -> File:
    result = await db.execute(
        select(File).where(File.id == file_id, File.user_id == user_id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise ValueError("File not found")
    file_record.tags = tags
    await db.flush()
    return file_record


async def toggle_favorite(
    db: AsyncSession, user_id: int, file_id: int
) -> File:
    result = await db.execute(
        select(File).where(File.id == file_id, File.user_id == user_id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise ValueError("File not found")
    file_record.is_favorite = not file_record.is_favorite
    await db.flush()
    return file_record


async def trash_file(db: AsyncSession, user_id: int, file_id: int) -> File:
    result = await db.execute(
        select(File).where(File.id == file_id, File.user_id == user_id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise ValueError("File not found")
    file_record.status = "trash"
    file_record.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    return file_record


async def restore_file(db: AsyncSession, user_id: int, file_id: int) -> File:
    result = await db.execute(
        select(File).where(File.id == file_id, File.user_id == user_id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise ValueError("File not found")
    file_record.status = "active"
    file_record.deleted_at = None
    await db.flush()
    return file_record


async def permanent_delete(db: AsyncSession, user_id: int, file_id: int):
    result = await db.execute(
        select(File).where(File.id == file_id, File.user_id == user_id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise ValueError("File not found")

    try:
        minio_client.remove_object(file_record.bucket, file_record.object_key)
    except Exception:
        pass

    await db.delete(file_record)
    await db.flush()


async def rename_file(db: AsyncSession, user_id: int, file_id: int, new_name: str) -> File:
    result = await db.execute(
        select(File).where(File.id == file_id, File.user_id == user_id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise ValueError("File not found")
    file_record.original_name = new_name
    await db.flush()
    await db.refresh(file_record)
    return file_record


async def move_file(db: AsyncSession, user_id: int, file_id: int, new_folder_path: str) -> File:
    result = await db.execute(
        select(File).where(File.id == file_id, File.user_id == user_id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise ValueError("File not found")
    file_record.folder_path = new_folder_path
    await db.flush()
    await db.refresh(file_record)
    return file_record
