"""Periodic jobs owned by the todo plugin."""

from core.scheduler import PeriodicJob
from plugins.todo.backend.reminders import check_todo_reminders

JOBS = [
    PeriodicJob(
        key="todo.reminders",
        owner="todo",
        handler=check_todo_reminders,
        interval_seconds=60,
        timeout_seconds=120,
        run_on_start=True,
    ),
]
