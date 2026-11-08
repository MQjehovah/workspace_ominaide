"""Schedule plugin startup hooks."""

from __future__ import annotations

from core.events.bus import subscribe
from core.jobs.service import enqueue
from core.logging import get_logger
from plugins.schedule.backend.external_sync import on_calendar_event

log = get_logger(__name__)

_subscribed = False


async def startup() -> None:
    global _subscribed
    if not _subscribed:
        subscribe(on_calendar_event)
        _subscribed = True
    await enqueue("schedule.external.backfill", {"days": 7})
    log.info("[schedule] external calendar event handler registered")
