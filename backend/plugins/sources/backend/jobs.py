"""Periodic information-source refresh owned by the sources plugin."""

from core.config.settings import settings
from core.scheduler import PeriodicJob


async def refresh_due_sources_job() -> dict:
    if not settings.sources_refresh_enabled:
        return {"skipped": True, "reason": "disabled"}
    from plugins.sources.backend.service import refresh_due_sources

    result = await refresh_due_sources(settings.sources_refresh_interval_seconds)
    if result.get("new"):
        from core.logging import get_logger

        get_logger(__name__).info("[sources] fetched %s new item(s)", result["new"])
    return result


JOBS = [
    PeriodicJob(
        key="sources.refresh_due",
        owner="sources",
        handler=refresh_due_sources_job,
        interval_seconds=max(60, int(settings.sources_refresh_interval_seconds)),
        timeout_seconds=1200,
        run_on_start=True,
    ),
]
