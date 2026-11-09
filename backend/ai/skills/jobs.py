"""Core hourly daily-brief generation.

A coordinator job fans out one job per user so the multi-worker executor can
render users in parallel. The per-user job also produces the workbench prompts.
"""

from __future__ import annotations

from core.jobs.service import enqueue, register_handler
from core.scheduler import PeriodicJob
from ai.skills import brief_cache


async def enqueue_daily_briefs() -> dict:
    bucket = brief_cache.hour_key()
    user_ids = await brief_cache.all_user_ids()
    for user_id in user_ids:
        await enqueue(
            "core.daily_brief.user",
            {"user_id": int(user_id)},
            idempotency_key=f"brief:{user_id}:{bucket}",
        )
    return {"users": len(user_ids), "bucket": bucket}


async def refresh_user_brief(job) -> dict:
    user_id = int((job.payload or {}).get("user_id") or 0)
    if not user_id:
        return {"skipped": True, "reason": "missing user_id"}
    payload = await brief_cache.refresh_user(user_id)
    return {"user_id": user_id, "day": payload.get("day")}


register_handler("core.daily_brief.user", refresh_user_brief)

JOBS = [
    PeriodicJob(
        key="core.daily_brief",
        owner="core",
        handler=enqueue_daily_briefs,
        interval_seconds=3600,
        timeout_seconds=300,
        run_on_start=True,
    ),
]
