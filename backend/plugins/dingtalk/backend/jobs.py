"""Periodic jobs owned by the DingTalk plugin."""

from core.scheduler import PeriodicJob
from plugins.dingtalk.backend.sync_calendar import sync_calendar
from plugins.dingtalk.backend.sync_unread import sync_unread
from plugins.dingtalk.backend.sync_chat import sync_chat

JOBS = [
    PeriodicJob(
        key="dingtalk.sync_chat",
        owner="dingtalk",
        handler=sync_chat,
        interval_seconds=24 * 60 * 60,
        timeout_seconds=900,
        run_on_start=True,
    ),
    PeriodicJob(
        key="dingtalk.sync_unread",
        owner="dingtalk",
        handler=sync_unread,
        interval_seconds=5 * 60,
        timeout_seconds=300,
        run_on_start=True,
    ),
    PeriodicJob(
        key="dingtalk.sync_calendar",
        owner="dingtalk",
        handler=sync_calendar,
        interval_seconds=60 * 60,
        timeout_seconds=600,
        run_on_start=True,
    ),
]
