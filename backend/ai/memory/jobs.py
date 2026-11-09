"""Daily memory curation job."""

from __future__ import annotations

from datetime import datetime

from ai.memory.curator import curate_user
from core.jobs.service import enqueue, register_handler
from core.scheduler import PeriodicJob


async def enqueue_memory_curation() -> dict:
    from core.auth.domain.models import User
    from core.database.session import async_session
    from sqlalchemy import select

    async with async_session() as db:
        user_ids = list((await db.execute(select(User.id))).scalars().all())
    bucket = datetime.now().strftime("%Y%m%d")
    for user_id in user_ids:
        await enqueue(
            "memory.curate.user",
            {"user_id": int(user_id)},
            idempotency_key=f"memory:curate:{user_id}:{bucket}",
        )
    return {"users": len(user_ids), "bucket": bucket}


async def curate_user_job(job) -> dict:
    user_id = int((job.payload or {}).get("user_id") or 0)
    if not user_id:
        return {"skipped": True}
    return await curate_user(user_id)


register_handler("memory.curate.user", curate_user_job)

JOBS = [
    PeriodicJob(
        key="memory.curate",
        owner="core",
        handler=enqueue_memory_curation,
        interval_seconds=86400,
        timeout_seconds=300,
        run_on_start=False,
    ),
]
