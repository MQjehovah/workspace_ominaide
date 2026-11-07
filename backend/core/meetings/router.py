from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database.session import get_db
from core.meetings.models import MeetingMinutesJob
from core.meetings.service import delete_job, schedule_job

router = APIRouter(prefix="/api/meetings", tags=["meetings"])

_AUDIO_EXT = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".webm", ".mp4",
}


class MinutesCreate(BaseModel):
    file_id: int
    title: str | None = Field(default=None, max_length=300)
    event_id: int | None = None
    language: str | None = Field(default=None, max_length=20)


def _serialize(job: MeetingMinutesJob, *, detail: bool = False) -> dict:
    data = {
        "id": job.id,
        "file_id": job.file_id,
        "event_id": job.event_id,
        "title": job.title,
        "status": job.status,
        "error": job.error,
        "note_id": job.note_id,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "minutes": job.minutes,
    }
    if detail:
        data["transcript"] = job.transcript
        data["segments"] = job.segments
    return data


@router.post("/minutes", status_code=202)
async def create_minutes(
    req: MinutesCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from plugins.files.backend.models import File

    file_record = (
        await db.execute(
            select(File).where(
                File.id == req.file_id,
                File.user_id == user["id"],
                File.status == "active",
            )
        )
    ).scalar_one_or_none()
    if file_record is None:
        raise HTTPException(404, detail="录音文件不存在")
    suffix = Path(file_record.original_name or "").suffix.lower()
    mime = (file_record.mime_type or "").lower()
    if not (mime.startswith("audio/") or mime.startswith("video/") or suffix in _AUDIO_EXT):
        raise HTTPException(422, detail="该文件不是音频或视频")

    tags = set(file_record.tags or [])
    tags.add("meeting_audio")
    file_record.tags = sorted(tags)

    now = datetime.now()
    title = (req.title or f"会议纪要 {now:%Y-%m-%d %H:%M}").strip()
    job = MeetingMinutesJob(
        user_id=user["id"],
        file_id=file_record.id,
        event_id=req.event_id,
        title=title[:300],
        language=req.language,
        status="queued",
    )
    db.add(job)
    await db.flush()
    await db.commit()
    await db.refresh(job)
    schedule_job(job.id)
    return _serialize(job)


@router.get("/minutes")
async def list_minutes(
    limit: int = Query(30, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(MeetingMinutesJob)
            .where(MeetingMinutesJob.user_id == user["id"])
            .order_by(MeetingMinutesJob.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {"items": [_serialize(row) for row in rows]}


@router.get("/minutes/{job_id}")
async def get_minutes(
    job_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = (
        await db.execute(
            select(MeetingMinutesJob).where(
                MeetingMinutesJob.id == job_id,
                MeetingMinutesJob.user_id == user["id"],
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(404, detail="任务不存在")
    return _serialize(job, detail=True)


@router.post("/minutes/{job_id}/retry", status_code=202)
async def retry_minutes(
    job_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = (
        await db.execute(
            select(MeetingMinutesJob).where(
                MeetingMinutesJob.id == job_id,
                MeetingMinutesJob.user_id == user["id"],
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(404, detail="任务不存在")
    if job.status != "failed":
        raise HTTPException(409, detail="只有失败的任务可以重试")
    job.status = "queued"
    job.error = None
    job.transcript = None
    job.segments = None
    job.minutes = None
    job.note_id = None
    job.finished_at = None
    await db.flush()
    await db.commit()
    await db.refresh(job)
    schedule_job(job.id)
    return _serialize(job)


@router.delete("/minutes/{job_id}")
async def remove_minutes(
    job_id: int,
    delete_audio: bool = Query(True),
    user: dict = Depends(get_current_user),
):
    ok = await delete_job(job_id, user["id"], delete_audio=delete_audio)
    if not ok:
        raise HTTPException(404, detail="任务不存在")
    return {"message": "Deleted", "audio_deleted": delete_audio}
