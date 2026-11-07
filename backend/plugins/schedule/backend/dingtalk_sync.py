"""Mirror DingTalk calendar events into the local schedule (no LLM)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_, select

from core.database.session import async_session
from core.timeutil import naive_local
from plugins.schedule.backend.models import Event


def _unwrap(payload, key: str):
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    for _ in range(5):
        if isinstance(data, dict) and key in data:
            return data[key]
        if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
            data = data["data"]
            continue
        if isinstance(data, dict) and isinstance(data.get("result"), (dict, list)):
            data = data["result"]
            continue
        break
    return []


def _event_time(value, fallback_end: bool = False) -> datetime | None:
    if not isinstance(value, dict):
        return None
    raw = value.get("dateTime") or value.get("date")
    if not raw:
        return None
    if len(str(raw)) == 10:
        raw = f"{raw}T{'23:59:59' if fallback_end else '00:00:00'}"
    try:
        return naive_local(raw)
    except Exception:
        return None


def _attendees(meta: dict) -> list[dict]:
    return [
        {
            "name": item.get("displayName"),
            "response": item.get("responseStatus"),
            "optional": bool(item.get("optional")),
            "self": bool(item.get("self")),
        }
        for item in meta.get("attendees") or []
        if isinstance(item, dict)
    ]


def _external_meta(raw: dict, location: str | None) -> dict:
    rooms = [
        {"name": room.get("roomName"), "status": room.get("responseStatus")}
        for room in (raw.get("meetingRooms") or [])
        if isinstance(room, dict)
    ]
    online = raw.get("onlineMeetingInfo") or {}
    extra = online.get("extraInfo") or {}
    organizer = raw.get("organizer") or {}
    return {
        "organizer": organizer.get("displayName"),
        "attendees": _attendees(raw),
        "rooms": rooms,
        "location": location,
        "meeting_url": online.get("url"),
        "meeting_room_code": extra.get("roomCode"),
        "timezone": (raw.get("start") or {}).get("timeZone"),
        "dingtalk_status": raw.get("status"),
        "free_busy": raw.get("freeBusy"),
        "categories": raw.get("categories") or [],
        "ical_uid": raw.get("iCalUID"),
        "series_master_id": raw.get("seriesMasterId"),
        "dingtalk_description": raw.get("description") or "",
    }


async def _upsert_event(user_id: int, raw: dict) -> str:
    external_id = str(raw.get("id") or raw.get("iCalUID") or "").strip()
    title = str(raw.get("summary") or raw.get("title") or "").strip()
    start = _event_time(raw.get("start"))
    if not external_id or not title or start is None:
        return "skipped"
    end = _event_time(raw.get("end"), fallback_end=True)
    status = "cancelled" if str(raw.get("status") or "").lower() == "cancelled" else "confirmed"
    rooms = [
        str(room.get("roomName") or "").strip()
        for room in (raw.get("meetingRooms") or [])
        if isinstance(room, dict)
    ]
    location = str(raw.get("location") or "").strip() or "、".join(filter(None, rooms)) or None
    meta = _external_meta(raw, location)
    now = datetime.now()

    async with async_session() as db:
        row = (await db.execute(
            select(Event).where(
                Event.user_id == user_id,
                Event.source == "dingtalk",
                Event.external_id == external_id,
            )
        )).scalar_one_or_none()

        # Adopt an earlier assistant-created copy instead of duplicating it.
        if row is None:
            q = select(Event).where(
                Event.user_id == user_id,
                Event.start_time == start,
                Event.external_id.is_(None),
                or_(Event.source == "dingtalk", Event.notes.ilike("钉钉同步%")),
            )
            if end is not None:
                q = q.where(Event.end_time == end)
            candidates = list((await db.execute(q.order_by(Event.id.desc()))).scalars().all())
            if candidates:
                row = candidates[0]
                row.source = "dingtalk"
                row.external_id = external_id

        created = row is None
        if row is None:
            row = Event(
                user_id=user_id,
                title=title[:200],
                start_time=start,
                end_time=end,
                notes="",
                source="dingtalk",
                external_id=external_id,
                location=location,
                status=status,
                external_meta=meta,
                last_synced_at=now,
            )
            db.add(row)
        else:
            row.title = title[:200]
            row.start_time = start
            row.end_time = end
            row.location = location
            row.status = status
            row.external_meta = meta
            row.last_synced_at = now
        await db.commit()
    return "created" if created else "updated"


async def sync_dingtalk_calendar(
    user_ids: list[int] | None = None,
    *,
    days_before: int = 7,
    days_after: int = 90,
) -> dict:
    from core.mcp_hub.models import McpServer
    from core.paths import dingtalk_env
    from mcp_servers.dingtalk.dws_client import run_dws

    if user_ids is None:
        async with async_session() as db:
            rows = list((await db.execute(
                select(McpServer.user_id).where(
                    McpServer.slug.like("dingtalk%"),
                    McpServer.enabled == True,  # noqa: E712
                )
            )).scalars().all())
        # Never fall back to user 1: unauthenticated users get no data at all.
        user_ids = sorted({int(row) for row in rows})

    now = datetime.now().astimezone().replace(microsecond=0)
    start = (now - timedelta(days=max(0, days_before))).isoformat()
    end = (now + timedelta(days=max(1, days_after))).isoformat()
    counts = {"created": 0, "updated": 0, "skipped": 0, "users": len(user_ids)}
    errors: list[str] = []

    for user_id in user_ids:
        try:
            payload = await run_dws(
                ["calendar", "event", "list", "--start", start, "--end", end, "--format", "json"],
                timeout=180,
                env=dingtalk_env(user_id),
            )
            events = _unwrap(payload, "events") or []
        except Exception as e:
            print(f"[schedule.sync] dingtalk calendar user {user_id} failed: {e}")
            errors.append(f"{user_id}: {str(e)[:200]}")
            continue

        for raw in events:
            if not isinstance(raw, dict):
                continue
            try:
                result = await _upsert_event(user_id, raw)
                counts[result] = counts.get(result, 0) + 1
            except Exception as e:
                print(f"[schedule.sync] event {raw.get('id')} failed: {e}")
                counts["skipped"] += 1

    if errors:
        counts["error"] = "; ".join(errors)[:300]
    if counts.get("created") or counts.get("updated"):
        print(f"[schedule.sync] dingtalk calendar: {counts}")
    return counts
