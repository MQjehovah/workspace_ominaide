import asyncio
import io
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from minio import Minio
from core.ai.indexer import index_content
from core.config.settings import settings
from core.minio.client import minio_client, public_minio_url
from plugins.files.backend.models import File
from plugins.files.backend.schemas import UploadUrlRequest, FileQueryParams, CreateFolderRequest


DEFAULT_BUCKET = "user-files"
UPLOAD_URL_EXPIRY = 600
DOWNLOAD_URL_EXPIRY = 1800


def _normalize_path(path: str | None) -> str:
    p = (path or "/").strip()
    if not p.startswith("/"):
        p = "/" + p
    return p.rstrip("/") or "/"


def _join_path(parent: str | None, name: str) -> str:
    parent = _normalize_path(parent)
    name = (name or "").strip("/")
    return f"{parent.rstrip('/')}/{name}" if parent != "/" else f"/{name}"


async def _emit_sync_change(
    db: AsyncSession, user_id: int, event_type: str, file_record: File,
    file_id: int | None = None,
) -> None:
    """Publish a change to enabled sync folders (best-effort, never blocks files)."""
    try:
        from plugins.sync.backend.service import notify_file_change

        await notify_file_change(
            db,
            user_id,
            event_type,
            _join_path(file_record.folder_path, file_record.original_name),
            file_id=file_id if file_id is not None else file_record.id,
            file_size=file_record.size,
        )
    except Exception as e:
        print(f"[files] sync event error: {e}")


def _generate_object_key(user_id: int, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    unique = uuid.uuid4().hex
    return f"{user_id}/{unique}{'.' + ext if ext else ''}"


async def create_folder(
    db: AsyncSession, user_id: int, req: CreateFolderRequest
) -> File:
    bucket = DEFAULT_BUCKET
    object_key = f"folder:{user_id}/{uuid.uuid4().hex}"

    folder = File(
        user_id=user_id,
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
    await _emit_sync_change(db, user_id, "created", folder)
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

    return public_minio_url(upload_url), file_record.id, object_key


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

    asyncio.create_task(index_content(
        user_id=user_id,
        source_type='file',
        source_id=file_record.id,
        title=file_record.original_name,
        content=str(file_record.id),
        metadata={"link": f"/files/{file_record.id}"},
    ))

    await _emit_sync_change(db, user_id, "created", file_record)
    return file_record


async def get_files(
    db: AsyncSession, user_id: int, params: FileQueryParams
) -> tuple[list[File], int]:
    query = select(File).where(File.user_id == user_id)

    if params.status:
        query = query.where(File.status == params.status)
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
    if params.search:
        like = f"%{params.search}%"
        query = query.where(or_(File.original_name.ilike(like), File.mime_type.ilike(like)))



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


async def save_generated_file(
    db: AsyncSession,
    user_id: int,
    filename: str,
    data: bytes,
    mime_type: str,
    folder_path: str = "/",
    index_text: str = "",
) -> File:
    """Persist an in-memory generated file (docx/pptx/...) to MinIO + metadata."""
    from core.auth.domain.models import User  # noqa: F401  (FK target for File.user_id)

    if minio_client is None:
        raise RuntimeError("MinIO unavailable")
    bucket = DEFAULT_BUCKET
    object_key = _generate_object_key(user_id, filename)
    minio_client.put_object(
        bucket,
        object_key,
        io.BytesIO(data),
        len(data),
        content_type=mime_type,
    )

    file_record = File(
        user_id=user_id,
        bucket=bucket,
        object_key=object_key,
        original_name=filename,
        folder_path=_normalize_path(folder_path),
        size=len(data),
        mime_type=mime_type,
        status="active",
    )
    db.add(file_record)
    await db.flush()
    await db.refresh(file_record)

    if index_text:
        asyncio.create_task(index_content(
            user_id=user_id,
            source_type='file',
            source_id=file_record.id,
            title=filename,
            content=index_text[:32000],
            metadata={"link": f"/files/{file_record.id}"},
        ))

    await _emit_sync_change(db, user_id, "created", file_record)
    return file_record


async def get_download_url(file_record: File) -> str:
    if not minio_client:
        return ""
    url = minio_client.presigned_get_object(
        file_record.bucket,
        file_record.object_key,
        expires=timedelta(seconds=DOWNLOAD_URL_EXPIRY),
    )
    return public_minio_url(url)


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
    await _emit_sync_change(db, user_id, "deleted", file_record)
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
    await _emit_sync_change(db, user_id, "created", file_record)
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

    await _emit_sync_change(db, user_id, "deleted", file_record, file_id=None)
    await db.delete(file_record)
    await db.flush()

    # Don't leave deleted files retrievable through semantic search.
    try:
        from core.ai import vector_store

        await vector_store.delete_source(user_id, "file", file_id)
    except Exception:
        pass


async def _rewrite_descendant_paths(
    db: AsyncSession, user_id: int, old_path: str, new_path: str, exclude_id: int | None = None
) -> None:
    """Move every descendant of a renamed/moved folder to the new prefix."""
    old_prefix = old_path.rstrip("/")
    rows = await db.execute(
        select(File).where(
            File.user_id == user_id,
            or_(File.folder_path == old_prefix, File.folder_path.like(f"{old_prefix}/%")),
        )
    )
    for child in rows.scalars().all():
        if exclude_id is not None and child.id == exclude_id:
            continue
        suffix = (child.folder_path or "").rstrip("/")[len(old_prefix):]
        child.folder_path = f"{new_path.rstrip('/')}{suffix}" or "/"


async def rename_file(db: AsyncSession, user_id: int, file_id: int, new_name: str) -> File:
    result = await db.execute(
        select(File).where(File.id == file_id, File.user_id == user_id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise ValueError("File not found")
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValueError("Empty name")
    if file_record.is_folder:
        old_path = _join_path(file_record.folder_path, file_record.original_name)
        new_path = _join_path(file_record.folder_path, new_name)
        await _rewrite_descendant_paths(db, user_id, old_path, new_path, exclude_id=file_record.id)
    file_record.original_name = new_name
    await db.flush()
    await db.refresh(file_record)
    await _emit_sync_change(db, user_id, "renamed", file_record)
    return file_record


async def move_file(db: AsyncSession, user_id: int, file_id: int, new_folder_path: str) -> File:
    result = await db.execute(
        select(File).where(File.id == file_id, File.user_id == user_id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise ValueError("File not found")
    new_folder_path = _normalize_path(new_folder_path)
    if file_record.is_folder:
        old_path = _join_path(file_record.folder_path, file_record.original_name)
        if new_folder_path == old_path or new_folder_path.startswith(old_path + "/"):
            raise ValueError("Cannot move a folder into itself")
        new_path = _join_path(new_folder_path, file_record.original_name)
        await _rewrite_descendant_paths(db, user_id, old_path, new_path, exclude_id=file_record.id)
    file_record.folder_path = new_folder_path
    await db.flush()
    await db.refresh(file_record)
    await _emit_sync_change(db, user_id, "moved", file_record)
    return file_record
