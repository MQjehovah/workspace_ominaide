from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from core.auth.dependencies import get_current_user
from core.database.session import async_session
from core.jobs.models import BackgroundJob
from core.jobs.service import enqueue

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobCreate(BaseModel):
    kind: str
    payload: dict | None = None
    idempotency_key: str | None = None
    run_after: datetime | None = None
    max_attempts: int = 3


def _out(job: BackgroundJob) -> dict:
    return {
        "id": job.id,
        "user_id": job.user_id,
        "kind": job.kind,
        "status": job.status,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "payload": job.payload,
        "result": job.result,
        "error": job.error,
        "run_after": job.run_after.isoformat() if job.run_after else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


@router.post("")
async def create_job(req: JobCreate, user: dict = Depends(get_current_user)):
    job = await enqueue(
        req.kind,
        req.payload or {},
        user_id=user["id"],
        idempotency_key=req.idempotency_key,
        run_after=req.run_after,
        max_attempts=req.max_attempts,
    )
    return _out(job)


@router.get("")
async def list_jobs(
    limit: int = Query(50, ge=1, le=200),
    status: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    async with async_session() as db:
        query = select(BackgroundJob).where(BackgroundJob.user_id == user["id"])
        if status:
            query = query.where(BackgroundJob.status == status)
        query = query.order_by(BackgroundJob.id.desc()).limit(limit)
        rows = (await db.execute(query)).scalars().all()
    return {"items": [_out(job) for job in rows]}


@router.post("/{job_id}/retry")
async def retry_job(job_id: int, user: dict = Depends(get_current_user)):
    async with async_session() as db:
        job = await db.get(BackgroundJob, job_id)
        if job is None or job.user_id != user["id"]:
            raise HTTPException(404, detail="任务不存在")
        if job.status not in {"failed", "dead"}:
            raise HTTPException(409, detail="只有失败任务可以重试")
        job.status = "queued"
        job.error = None
        job.run_after = datetime.now()
        await db.commit()
        await db.refresh(job)
    return _out(job)


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: int, user: dict = Depends(get_current_user)):
    async with async_session() as db:
        job = await db.get(BackgroundJob, job_id)
        if job is None or job.user_id != user["id"]:
            raise HTTPException(404, detail="任务不存在")
        if job.status in {"done", "dead"}:
            raise HTTPException(409, detail="任务已结束")
        job.status = "cancelled"
        job.locked_at = None
        await db.commit()
        await db.refresh(job)
    return _out(job)
