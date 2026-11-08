"""Consume neutral external-calendar events and mirror them into schedule."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from core.database.session import async_session
from core.events.models import UserActivity
from core.logging import get_logger
from core.timeutil import naive_local
from plugins.schedule.backend.models import Event

log = get_logger(__name__)

_UPSERT = "calendar.external.upsert"
_DELETE = "calendar.external.delete"


def _dt(value) -> datetime | None:
    if not value:
        return None
    try:
        return naive_local(value)
    except Exception:
        return None


async def sync_external_calendar() -> dict:
    since = datetime.now() - timedelta(days=2)
    async with async_session() as db:
        events = list((await db.execute(
            select(UserActivity)
            .where(
                UserActivity.event_type.in_((_UPSERT, _DELETE)),
                UserActivity.created_at >= since,
            )
            .order_by(UserActivity.id.desc())
            .limit(5000)
        )).scalars().all())
    events.reverse()

    counts = {"created": 0, "updated": 0, "deleted": 0, "skipped": 0, "processed": 0}
    for event in events:
        details = event.details if isinstance(event.details, dict) else {}
        provider = str(details.get("provider") or "external")
        external_id = str(details.get("external_id") or "").strip()
        if not external_id:
            counts["skipped"] += 1
            continue
        title = str(details.get("title") or "").strip()
        start = _dt(details.get("start"))
        end = _dt(details.get("end"))
        applied_at = event.created_at or datetime.now()
        if event.event_type == _UPSERT and (not title or start is None):
            counts["skipped"] += 1
            continue
        async with async_session() as db:
            row = (await db.execute(
                select(Event).where(
                    Event.user_id == event.user_id,
                    Event.source == provider,
                    Event.external_id == external_id,
                )
            )).scalar_one_or_none()
            if (
                row is not None
                and row.last_synced_at is not None
                and event.created_at is not None
                and row.last_synced_at >= event.created_at
            ):
                counts["skipped"] += 1
                continue
            created = row is None
            if row is None:
                if event.event_type == _DELETE:
                    counts["skipped"] += 1
                    continue
                row = Event(
                    user_id=event.user_id,
                    title=title[:200],
                    start_time=start,
                    end_time=end,
                    notes="",
                    source=provider,
                    external_id=external_id,
                    location=details.get("location"),
                    status="confirmed",
                    external_meta=details.get("metadata") or {},
                    last_synced_at=applied_at,
                )
                db.add(row)
            else:
                row.title = title[:200] or row.title
                row.start_time = start or row.start_time
                row.end_time = end
                row.location = details.get("location")
                row.external_meta = details.get("metadata") or row.external_meta
                row.last_synced_at = applied_at
                if event.event_type == _DELETE:
                    row.status = "cancelled"
            await db.commit()
        counts["processed"] += 1
        if event.event_type == _DELETE:
            counts["deleted"] += 1
        else:
            counts["created" if created else "updated"] += 1
    return counts
