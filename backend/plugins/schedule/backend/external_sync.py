"""Apply neutral external-calendar events to the schedule plugin.

Events are delivered through the core event bus. The callback only enqueues a
retryable background job; the job applies the change idempotently. Startup
backfill covers events published while the backend was offline.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from sqlalchemy import select

from core.database.session import async_session
from core.events.models import UserActivity
from core.jobs.service import enqueue
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


def _fingerprint(event: dict) -> str:
    payload = {
        key: event.get(key)
        for key in ("title", "start", "end", "location", "status", "metadata")
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


async def _apply_event(activity: UserActivity) -> str:
    details = activity.details if isinstance(activity.details, dict) else {}
    provider = str(details.get("provider") or "external")
    external_id = str(details.get("external_id") or "").strip()
    if not external_id:
        return "skipped"

    title = str(details.get("title") or "").strip()
    start = _dt(details.get("start"))
    end = _dt(details.get("end"))
    if activity.event_type == _UPSERT and (not title or start is None):
        return "skipped"

    async with async_session() as db:
        row = (await db.execute(
            select(Event).where(
                Event.user_id == activity.user_id,
                Event.source == provider,
                Event.external_id == external_id,
            )
        )).scalar_one_or_none()
        if (
            row is not None
            and row.last_synced_at is not None
            and activity.created_at is not None
            and row.last_synced_at >= activity.created_at
        ):
            return "skipped"

        applied_at = activity.created_at or datetime.now()
        if row is None:
            if activity.event_type == _DELETE:
                return "skipped"
            row = Event(
                user_id=activity.user_id,
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
            result = "created"
        else:
            row.title = title[:200] or row.title
            row.start_time = start or row.start_time
            row.end_time = end
            row.location = details.get("location")
            row.external_meta = details.get("metadata") or row.external_meta
            row.last_synced_at = applied_at
            if activity.event_type == _DELETE:
                row.status = "cancelled"
                result = "deleted"
            else:
                result = "updated"
        await db.commit()
        return result


async def on_calendar_event(activity: UserActivity) -> None:
    if activity.event_type not in (_UPSERT, _DELETE):
        return
    await enqueue(
        "schedule.external.apply",
        {"activity_id": activity.id},
        idempotency_key=f"calendar:activity:{activity.id}",
        max_attempts=5,
    )


async def apply_external_event(job) -> dict:
    activity_id = int((job.payload or {}).get("activity_id") or 0)
    if not activity_id:
        return {"skipped": True, "reason": "missing activity_id"}
    async with async_session() as db:
        activity = await db.get(UserActivity, activity_id)
    if activity is None or activity.event_type not in (_UPSERT, _DELETE):
        return {"skipped": True, "reason": "activity not found"}
    result = await _apply_event(activity)
    return {"activity_id": activity_id, "result": result}


async def backfill_external_calendar(job) -> dict:
    days = int((job.payload or {}).get("days") or 7)
    since = datetime.now() - timedelta(days=max(1, days))
    async with async_session() as db:
        activities = list((await db.execute(
            select(UserActivity)
            .where(
                UserActivity.event_type.in_((_UPSERT, _DELETE)),
                UserActivity.created_at >= since,
            )
            .order_by(UserActivity.id.asc())
        )).scalars().all())

    counts = {"created": 0, "updated": 0, "deleted": 0, "skipped": 0}
    for activity in activities:
        try:
            result = await _apply_event(activity)
            counts[result] = counts.get(result, 0) + 1
        except Exception as exc:
            log.warning("calendar backfill activity %s failed: %s", activity.id, exc)
            counts["skipped"] += 1
    return {"events": len(activities), **counts}
