"""Hourly activity analysis jobs."""

from ai.activity_insights import service
from core.jobs.service import register_handler
from core.scheduler import PeriodicJob


async def analyze_user_job(job) -> dict:
    user_id = int((job.payload or {}).get("user_id") or 0)
    if not user_id:
        return {"skipped": True, "reason": "missing user_id"}
    return await service.analyze_user(user_id)


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
