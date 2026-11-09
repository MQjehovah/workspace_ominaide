
from core.logging import get_logger
log = get_logger(__name__)
import io
import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, UploadFile, File, Request
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from core.auth.jwt import decode_access_token
from core.config.settings import settings
from core.events.recorder import record_event
from core.minio.client import public_minio_url
from core.pagination import decode_int_cursor, encode_cursor
from plugins.files.backend.schemas import (
    UploadUrlRequest, UploadUrlResponse, ConfirmUploadRequest,
    UpdateTagsRequest, FileQueryParams, FileResponse, FileListResponse,
    CreateFolderRequest, RenameFileRequest, MoveFileRequest,
)
from plugins.files.backend import service as file_service

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/note/{object_key:path}")
async def serve_note_file(object_key: str):
    """Serve a note attachment directly via MinIO proxy."""
    import mimetypes
    from core.minio.client import minio_client
    from fastapi.responses import StreamingResponse
    if not minio_client:
        raise HTTPException(status_code=503, detail="MinIO unavailable")
    try:
        obj = minio_client.get_object("user-files", object_key)
        data = obj.read()
        mime_type = mimetypes.guess_type(object_key)[0] or "application/octet-stream"
        return StreamingResponse(io.BytesIO(data), media_type=mime_type)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")


@router.post("/upload/direct")
async def direct_upload_file(
    file: UploadFile = File(...),
    folder_path: str = Query("/"),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file directly through the backend (no presigned URL)."""
    from core.minio.client import minio_client
    req = UploadUrlRequest(
        filename=file.filename or "untitled",
        mime_type=file.content_type or "application/octet-stream",
        folder_path=folder_path,
    )
    upload_url, file_id, object_key = await file_service.generate_upload_url(db, user["id"], req)
    if minio_client:
        upload = file.file
        upload.seek(0, os.SEEK_END)
        size = upload.tell()
        upload.seek(0)
        minio_client.put_object(
            "user-files",
            object_key,
            upload,
            size,
            content_type=req.mime_type or "application/octet-stream",
        )
    record = await file_service.confirm_upload(db, user["id"], file_id)
    return {"id": record.id, "object_key": object_key}


@router.post("/upload/note")
async def get_temp_upload_url(
    user: dict = Depends(get_current_user),
):
    """Get a presigned upload URL without creating a DB record. Used by notes plugin for images."""
    import uuid
    import os
    from core.minio.client import minio_client
    from datetime import timedelta
    if not minio_client:
        raise HTTPException(status_code=503, detail="MinIO unavailable")
    object_key = f"{user['id']}/{uuid.uuid4().hex}"
    upload_url = minio_client.presigned_put_object(
        "user-files", object_key, expires=timedelta(seconds=600)
    )
    upload_url = public_minio_url(upload_url)
    return {"upload_url": upload_url, "object_key": object_key}


@router.post("/upload/note/direct")
async def direct_upload_note_file(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Upload a file directly through the backend (no presigned URL). Used when MinIO is not publicly accessible."""
    import uuid
    from core.minio.client import minio_client
    if not minio_client:
        raise HTTPException(status_code=503, detail="MinIO unavailable")
    object_key = f"{user['id']}/{uuid.uuid4().hex}{Path(file.filename).suffix if file.filename else ''}"
    content = await file.read()
    minio_client.put_object("user-files", object_key, io.BytesIO(content), len(content))
    return {"upload_url": "", "object_key": object_key}


@router.post("/folder", response_model=FileResponse, status_code=201)
async def create_folder(
    req: CreateFolderRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    folder = await file_service.create_folder(db, user["id"], req)
    return FileResponse.model_validate(folder)


@router.post("/upload-url", response_model=UploadUrlResponse)
async def get_upload_url(
    req: UploadUrlRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    upload_url, file_id, object_key = await file_service.generate_upload_url(
        db, user["id"], req
    )
    if not settings.minio_public:
        upload_url = ""
    return UploadUrlResponse(upload_url=upload_url, file_id=file_id, object_key=object_key)


@router.post("/confirm", response_model=FileResponse)
async def confirm_upload(
    req: ConfirmUploadRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        file_record = await file_service.confirm_upload(db, user["id"], req.file_id)
        await record_event(db, user["id"], "file.uploaded", "file", file_record.id,
                           f"上传文件: {file_record.original_name}",
                           {"file_id": file_record.id, "name": file_record.original_name,
                            "size": file_record.size, "mime": file_record.mime_type})
        background_tasks.add_task(index_file_for_search, file_record, user["id"])
        return FileResponse.model_validate(file_record)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


async def index_file_for_search(file_record, user_id: int):
    try:
        from core.ai.qdrant_index import index_file
        from core.ai.text_extractor import extract_text
        from core.minio.client import minio_client
        import tempfile, os

        temp_dir = tempfile.gettempdir()
        safe_name = file_record.object_key.replace('/', '_').replace('\\', '_')
        local_path = os.path.join(temp_dir, f"idx_{file_record.id}_{safe_name}")

        try:
            minio_client.fget_object(file_record.bucket, file_record.object_key, local_path)
            content = await extract_text(local_path, file_record.mime_type)
            await index_file(
                file_id=file_record.id,
                user_id=user_id,
                filename=file_record.original_name,
                content=content,
                file_size=file_record.size,
            )
        finally:
            if os.path.exists(local_path):
                os.remove(local_path)
    except Exception:
        pass


@router.get("", response_model=FileListResponse)
async def list_files(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str = Query("active"),
    bucket: str | None = None,
    mime_type: str | None = None,
    favorite: bool | None = None,
    folder_path: str | None = None,
    is_folder: bool | None = None,
    search: str | None = None,
    cursor: str | None = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    params = FileQueryParams(
        page=page, page_size=page_size, status=status,
        bucket=bucket,
        mime_type=mime_type, favorite=favorite,
        folder_path=folder_path, is_folder=is_folder,
        search=search, cursor=decode_int_cursor(cursor),
    )
    files, total = await file_service.get_files(db, user["id"], params)
    return FileListResponse(
        files=[FileResponse.model_validate(f) for f in files],
        total=total,
        page=page,
        page_size=page_size,
        next_cursor=encode_cursor(files[-1].id) if len(files) >= page_size else None,
    )


@router.get("/{file_id}", response_model=FileResponse)
async def get_file(
    file_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    file_record = await file_service.get_file(db, user["id"], file_id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse.model_validate(file_record)


@router.get("/{file_id}/download-url")
async def get_download_url(
    file_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    file_record = await file_service.get_file(db, user["id"], file_id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    if settings.minio_public:
        url = await file_service.get_download_url(file_record)
    else:
        url = None
    return {"download_url": url, "filename": file_record.original_name, "file_id": file_id}


@router.post("/{file_id}/share")
async def share_file_link(
    file_id: int,
    expires_hours: int = Query(168, ge=1, le=24 * 30),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import timedelta
    from core.minio.client import minio_client, public_minio_url

    file_record = await file_service.get_file(db, user["id"], file_id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    if minio_client is None:
        raise HTTPException(status_code=503, detail="MinIO unavailable")
    url = minio_client.presigned_get_object(
        file_record.bucket,
        file_record.object_key,
        expires=timedelta(hours=expires_hours),
    )
    return {
        "url": public_minio_url(url),
        "filename": file_record.original_name,
        "expires_hours": expires_hours,
    }


@router.get("/{file_id}/download")
async def download_file(
    file_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Proxy download: stream file bytes through backend (MinIO not exposed)."""
    import mimetypes
    from core.minio.client import minio_client
    if not minio_client:
        raise HTTPException(status_code=503, detail="MinIO unavailable")
    file_record = await file_service.get_file(db, user["id"], file_id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        obj = minio_client.get_object(file_record.bucket, file_record.object_key)
        mime_type = mimetypes.guess_type(file_record.original_name)[0] or "application/octet-stream"

        def gen():
            while True:
                chunk = obj.read(32 * 1024)
                if not chunk:
                    break
                yield chunk

        from urllib.parse import quote
        filename_safe = quote(file_record.original_name)
        return StreamingResponse(gen(), media_type=mime_type,
                                 headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename_safe}"})
    except Exception:
        log.exception("download failed file_id=%s", file_id)
        raise HTTPException(status_code=404, detail="File not found in storage")


@router.get("/{file_id}/stream")
async def stream_file(
    file_id: int,
    request: Request,
    token: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """Stream a file with HTTP Range support for images, PDF, audio and video."""
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = int(payload["sub"])

    import mimetypes
    from core.minio.client import minio_client
    if not minio_client:
        raise HTTPException(status_code=503, detail="MinIO unavailable")

    file_record = await file_service.get_file(db, user_id, file_id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        mime_type = mimetypes.guess_type(file_record.original_name)[0] or "application/octet-stream"
        total = int(file_record.size or 0)
        range_header = request.headers.get("range") or ""
        start, end = 0, max(0, total - 1)
        status_code = 200
        headers = {"Accept-Ranges": "bytes"}
        length = 0

        if range_header.startswith("bytes=") and total > 0:
            raw = range_header[6:].split(",", 1)[0].strip()
            start_text, _, end_text = raw.partition("-")
            try:
                if start_text:
                    start = int(start_text)
                if end_text:
                    end = int(end_text)
            except ValueError:
                start, end = 0, total - 1
            start = max(0, min(start, total - 1))
            end = max(start, min(end, total - 1))
            length = end - start + 1
            status_code = 206
            headers["Content-Range"] = f"bytes {start}-{end}/{total}"

        if length > 0:
            obj = minio_client.get_object(
                file_record.bucket, file_record.object_key, offset=start, length=length
            )
        else:
            obj = minio_client.get_object(file_record.bucket, file_record.object_key)

        def gen():
            while True:
                chunk = obj.read(32 * 1024)
                if not chunk:
                    break
                yield chunk

        return StreamingResponse(gen(), status_code=status_code, media_type=mime_type, headers=headers)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found in storage")


@router.put("/{file_id}/tags", response_model=FileResponse)
async def update_tags(
    file_id: int,
    req: UpdateTagsRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        file_record = await file_service.update_tags(db, user["id"], file_id, req.tags)
        return FileResponse.model_validate(file_record)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{file_id}/favorite", response_model=FileResponse)
async def toggle_favorite(
    file_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        file_record = await file_service.toggle_favorite(db, user["id"], file_id)
        return FileResponse.model_validate(file_record)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{file_id}")
async def trash_file(
    file_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        f = await file_service.get_file(db, user["id"], file_id)
        await file_service.trash_file(db, user["id"], file_id)
        if f: await record_event(
            db, user["id"], "file.trashed", "file", file_id,
            f"删除文件: {f.original_name}",
            {"file_id": file_id, "name": f.original_name, "size": f.size},
        )
        return {"message": "File moved to trash"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{file_id}/restore", response_model=FileResponse)
async def restore_file(
    file_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        file_record = await file_service.restore_file(db, user["id"], file_id)
        return FileResponse.model_validate(file_record)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{file_id}/permanent")
async def permanent_delete(
    file_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await file_service.permanent_delete(db, user["id"], file_id)
        return {"message": "File permanently deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{file_id}/rename", response_model=FileResponse)
async def rename_file(
    file_id: int,
    req: RenameFileRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        existing = await file_service.get_file(db, user["id"], file_id)
        old_name = existing.original_name if existing else ""
        file_record = await file_service.rename_file(db, user["id"], file_id, req.new_name)
        await record_event(db, user["id"], "file.renamed", "file", file_id,
                           f"重命名文件: {file_record.original_name}",
                           {"file_id": file_id, "name": file_record.original_name,
                            "old_name": old_name})
        return FileResponse.model_validate(file_record)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{file_id}/move", response_model=FileResponse)
async def move_file(
    file_id: int,
    req: MoveFileRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        file_record = await file_service.move_file(db, user["id"], file_id, req.new_folder_path)
        await record_event(db, user["id"], "file.moved", "file", file_id,
                           f"移动文件: {file_record.original_name}",
                           {"file_id": file_id, "name": file_record.original_name,
                            "new_path": req.new_folder_path})
        return FileResponse.model_validate(file_record)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# File sync routes are mounted from the files plugin.
from plugins.files.backend.sync_router import router as sync_router  # noqa: E402,F401
