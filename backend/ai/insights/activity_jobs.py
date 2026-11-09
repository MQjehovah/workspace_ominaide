"""Hourly activity analysis jobs."""

from ai.insights import activity_service as service
from core.jobs.service import register_handler
from core.scheduler import PeriodicJob
from core.observability.context import set_user_id


async def analyze_user_job(job) -> dict:
    user_id = int((job.payload or {}).get("user_id") or 0)
    if not user_id:
        return {"skipped": True, "reason": "missing user_id"}
    set_user_id(user_id)
    try:
        return await service.analyze_user(user_id)
    finally:
        set_user_id(None)


register_handler("core.activity_analysis.user", analyze_user_job)

JOBS = [
    PeriodicJob(
        key="core.activity_analysis",
        owner="core",
        handler=service.enqueue_activity_analyses,
        interval_seconds=3600,
        timeout_seconds=300,
        run_on_start=True,
    ),
]
