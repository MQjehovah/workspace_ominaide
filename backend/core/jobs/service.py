from __future__ import annotations

from core.logging import get_logger
log = get_logger(__name__)

import asyncio
import time
from datetime import datetime, timedelta
from typing import Awaitable, Callable

from sqlalchemy import delete, select

from core.database.session import async_session
from core.jobs.models import BackgroundJob
from core.logging import get_logger

Handler = Callable[[BackgroundJob], Awaitable[None]]
_handlers: dict[str, Handler] = {}
_worker_tasks: list[asyncio.Task] = []
log = get_logger(__name__)


def register_handler(kind: str, handler: Handler) -> None:
    _handlers[kind] = handler


async def enqueue(
    kind: str,
    payload: dict | None = None,
    *,
    user_id: int | None = None,
    idempotency_key: str | None = None,
    run_after: datetime | None = None,
    max_attempts: int = 3,
) -> BackgroundJob:
    async with async_session() as db:
        if idempotency_key:
            existing = (
                await db.execute(
                    select(BackgroundJob).where(
                        BackgroundJob.idempotency_key == idempotency_key
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing
        job = BackgroundJob(
            user_id=user_id,
            kind=kind,
            payload=payload or {},
            status="queued",
            max_attempts=max(1, max_attempts),
            run_after=run_after or datetime.now(),
            idempotency_key=idempotency_key,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job


async def _claim_one() -> BackgroundJob | None:
    async with async_session() as db:
        query = (
            select(BackgroundJob)
            .where(
                BackgroundJob.status == "queued",
                (BackgroundJob.run_after == None)
                | (BackgroundJob.run_after <= datetime.now()),  # noqa: E711
            )
            .order_by(BackgroundJob.id)
            .limit(1)
        )
        try:
            query = query.with_for_update(skip_locked=True)
        except Exception:
            pass
        row = (await db.execute(query)).scalar_one_or_none()
        if row is None:
            return None
        row.status = "running"
        row.locked_at = datetime.now()
        row.attempts += 1
        await db.commit()
        await db.refresh(row)
        return row


async def _finish(
    job_id: int,
    *,
    status: str,
    result: dict | None = None,
    error: str | None = None,
    run_after: datetime | None = None,
) -> None:
    async with async_session() as db:
        job = await db.get(BackgroundJob, job_id)
        if job is None:
            return
        if job.status == "cancelled":
            return
        job.status = status
        job.result = result
        job.error = (error or "")[:3000] or None
        job.run_after = run_after
        job.locked_at = None
        await db.commit()


async def _run_job(job: BackgroundJob) -> None:
    handler = _handlers.get(job.kind)
    if handler is None:
        await _finish(job.id, status="failed", error=f"没有注册任务处理器: {job.kind}")
        return
    try:
        result = await handler(job)
    except Exception as exc:
        if job.attempts >= job.max_attempts:
            await _finish(
                job.id,
                status="dead",
                error=str(exc),
            )
        else:
            delay = min(300, 5 * (2 ** max(0, job.attempts - 1)))
            await _finish(
                job.id,
                status="queued",
                error=str(exc),
                run_after=datetime.now() + timedelta(seconds=delay),
            )
    else:
        await _finish(
            job.id,
            status="done",
            result=result if isinstance(result, dict) else {"ok": True},
        )


async def _cleanup() -> None:
    cutoff = datetime.now() - timedelta(days=14)
    try:
        from core.observability.models import RequestTrace

        async with async_session() as db:
            await db.execute(
                delete(RequestTrace).where(RequestTrace.created_at < cutoff)
            )
            await db.execute(
                delete(BackgroundJob).where(
                    BackgroundJob.status.in_(["done", "cancelled", "dead"]),
                    BackgroundJob.created_at < cutoff,
                )
            )
            await db.commit()
    except Exception as exc:
        log.warning("job cleanup failed: %s", exc)


async def worker_loop() -> None:
    last_cleanup = 0.0
    while True:
        if time.monotonic() - last_cleanup > 3600:
            last_cleanup = time.monotonic()
            await _cleanup()
        try:
            job = await _claim_one()
            if job is None:
                await asyncio.sleep(2)
                continue
            await _run_job(job)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning(f"[jobs] worker error: {exc}")
            await asyncio.sleep(5)


def start_workers(count: int | None = None) -> list[asyncio.Task]:
    """Start concurrent job workers.

    Async DB/HTTP handlers stay on the event loop; blocking calls inside a
    handler use ``asyncio.to_thread`` internally. SQLite is kept to one worker
    so tests do not hit write-lock contention.
    """
    global _worker_tasks
    if any(not task.done() for task in _worker_tasks):
        return _worker_tasks

    from core.config.settings import settings

    workers = int(settings.jobs_workers if count is None else count)
    if workers <= 0:
        log.info("[jobs] background workers disabled")
        _worker_tasks = []
        return _worker_tasks
    if "sqlite" in (getattr(settings, "database_url", "") or ""):
        workers = min(workers, 1)
    workers = max(1, min(workers, 16))
    _worker_tasks = [
        asyncio.create_task(worker_loop(), name=f"jobs-worker-{i + 1}")
        for i in range(workers)
    ]
    log.info(f"[jobs] started {workers} worker(s)")
    return _worker_tasks


def start_worker() -> asyncio.Task:
    """Backward-compatible single-worker entry point."""
    return start_workers()[0]


async def stop_workers() -> None:
    global _worker_tasks
    tasks = list(_worker_tasks)
    _worker_tasks = []
    for task in tasks:
        task.cancel()
    for task in tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass


async def stop_worker() -> None:
    await stop_workers()
