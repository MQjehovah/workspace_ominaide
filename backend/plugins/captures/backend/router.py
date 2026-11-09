from __future__ import annotations

import asyncio
import io
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from core.auth.dependencies import get_current_user
from plugins.captures.backend import service
from core.database.session import async_session

router = APIRouter(prefix="/api/captures", tags=["captures"])


class CaptureCreate(BaseModel):
    kind: str = "text"
    source: str = "web"
    url: str | None = None
    text: str | None = None
    title: str | None = None


class ConvertRequest(BaseModel):
    target: str
    params: dict | None = None


def _out(row) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "source": row.source,
        "url": row.url,
        "title": row.title,
        "content": row.content,
        "summary": row.summary,
        "key_points": row.key_points or [],
        "tags": row.tags or [],
        "people": row.people or [],
        "suggested_actions": row.suggested_actions or [],
        "file_id": row.file_id,
        "status": row.status,
        "error": row.error,
        "note_id": row.note_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.post("")
async def create_capture(req: CaptureCreate, user: dict = Depends(get_current_user)):
    try:
        row = await service.create_capture(
            user["id"],
            kind=req.kind,
            source=req.source,
            url=req.url,
            text=req.text,
            title=req.title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _out(row)


@router.post("/upload")
async def upload_capture(
    file: UploadFile = File(...),
    text: str = Form(""),
    title: str = Form(""),
    source: str = Form("web"),
    user: dict = Depends(get_current_user),
):
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件超过 25MB")
    from plugins.files.backend.models import File as FileModel

    from core.minio.client import minio_client

    if minio_client is None:
        raise HTTPException(status_code=503, detail="MinIO unavailable")
    suffix = Path(file.filename or "").suffix
    object_key = f"{user['id']}/captures/{uuid.uuid4().hex}{suffix}"
    mime = file.content_type or "application/octet-stream"
    try:
        await asyncio.to_thread(
            minio_client.put_object, "user-files", object_key,
            io.BytesIO(data), len(data), content_type=mime,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"上传失败: {exc}")
    async with async_session() as db:
        row = FileModel(
            user_id=user["id"],
            bucket="user-files",
            object_key=object_key,
            original_name=file.filename or "随手记附件",
            folder_path="/captures",
            size=len(data),
            mime_type=mime,
            status="active",
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        file_id = row.id
    kind = "image" if mime.startswith("image/") else "file"
    try:
        capture = await service.create_capture(
            user["id"], kind=kind, source=source,
            text=text, title=title or file.filename, file_id=file_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _out(capture)


@router.get("")
async def list_captures(
    status: str | None = Query(None),
    kind: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    rows = await service.list_captures(
        user["id"], status=status, kind=kind, limit=limit,
    )
    return {"items": [_out(row) for row in rows]}


@router.get("/{capture_id}")
async def get_capture(capture_id: int, user: dict = Depends(get_current_user)):
    row = await service.get_capture(user["id"], capture_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Capture not found")
    return _out(row)


@router.post("/{capture_id}/analyze")
async def reanalyze(capture_id: int, user: dict = Depends(get_current_user)):
    row = await service.get_capture(user["id"], capture_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Capture not found")
    from core.jobs.service import enqueue

    job = await enqueue(
        "capture.analyze", {"capture_id": capture_id}, user_id=user["id"],
        idempotency_key=f"capture:analyze:{capture_id}:{uuid.uuid4().hex}",
    )
    return {"message": "分析任务已提交", "job_id": job.id}


@router.post("/{capture_id}/convert")
async def convert_capture(
    capture_id: int, req: ConvertRequest, user: dict = Depends(get_current_user)
):
    try:
        result = await service.convert_capture(
            user["id"], capture_id, req.target, req.params,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result


@router.delete("/{capture_id}")
async def delete_capture(capture_id: int, user: dict = Depends(get_current_user)):
    ok = await service.delete_capture(user["id"], capture_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Capture not found")
    return {"message": "Deleted"}
