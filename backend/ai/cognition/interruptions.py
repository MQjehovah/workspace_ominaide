"""Interruption policy for proactive notifications.

A proposal may be created with ``channel="notification"`` or ``"voice"``.
This module decides whether interrupting the user right now is acceptable:

- quiet hours
- an ongoing calendar event
- the daily notification budget

When an interruption is suppressed the proposal is still created, but only
shown in-app (``channel="now"``) so nothing is lost.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from core.config.settings import settings


def _parse_hhmm(value: str) -> int | None:
    try:
        hours, minutes = value.strip().split(":")
        return int(hours) * 60 + int(minutes)
    except (ValueError, AttributeError):
        return None


def in_quiet_hours(now: datetime, spec: str | None = None) -> bool:
    raw = spec if spec is not None else settings.proposal_quiet_hours
    if not raw or "-" not in raw:
        return False
    start_raw, end_raw = raw.split("-", 1)
    start = _parse_hhmm(start_raw)
    end = _parse_hhmm(end_raw)
    if start is None or end is None:
        return False
    current = now.hour * 60 + now.minute
    if start == end:
        return False
    if start < end:
        return start <= current < end
    # Overnight window, e.g. 22:00-08:00.
    return current >= start or current < end


async def in_meeting(db, user_id: int, now: datetime) -> bool:
    from plugins.schedule.backend.models import Event

    row = (await db.execute(
        select(Event.id).where(
            Event.user_id == user_id,
            Event.start_time <= now,
            Event.end_time.is_not(None),
            Event.end_time > now,
            Event.status != "cancelled",
        ).limit(1)
    )).scalar_one_or_none()
    return row is not None


async def _notifications_today(db, user_id: int, now: datetime) -> int:
    from plugins.notifications.backend.models import Notification

    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    count = (await db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == user_id,
            Notification.type == "proposal",
            Notification.created_at >= start,
        )
    )).scalar_one()
    return int(count or 0)


async def decide_channel(db, user_id: int, channel: str, now: datetime | None = None) -> tuple[str, dict]:
    """Return the effective channel plus a decision trace."""
    if channel not in ("notification", "voice"):
        return channel, {}

    moment = now or datetime.now()
    if in_quiet_hours(moment):
        return "now", {"deferred": "quiet_hours", "channel": channel}
    if await in_meeting(db, user_id, moment):
        return "now", {"deferred": "in_meeting", "channel": channel}
    used = await _notifications_today(db, user_id, moment)
    if used >= max(1, int(settings.proposal_notify_daily_limit)):
        return "now", {"deferred": "daily_budget", "channel": channel, "used": used}
    return channel, {}
