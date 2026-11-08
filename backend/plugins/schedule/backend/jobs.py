"""Periodic jobs and job handlers owned by the schedule plugin."""

from core.jobs.service import register_handler
from core.scheduler import PeriodicJob
from plugins.schedule.backend.external_sync import (
    apply_external_event,
    backfill_external_calendar,
)
from plugins.schedule.backend.reminders import check_schedule_reminders

register_handler("schedule.external.apply", apply_external_event)
register_handler("schedule.external.backfill", backfill_external_calendar)

JOBS = [
    PeriodicJob(
        key="schedule.reminders",
        owner="schedule",
        handler=check_schedule_reminders,
        interval_seconds=60,
        timeout_seconds=120,
        run_on_start=True,
    ),
]
