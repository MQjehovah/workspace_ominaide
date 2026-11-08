"""Periodic jobs owned by the schedule plugin."""

from core.scheduler import PeriodicJob
from plugins.schedule.backend.external_sync import sync_external_calendar

JOBS = [
    PeriodicJob(
        key="schedule.sync_external_calendar",
        owner="schedule",
        handler=sync_external_calendar,
        interval_seconds=300,
        timeout_seconds=300,
    ),
]
