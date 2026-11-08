"""Fetch DingTalk calendar events and publish neutral external-calendar events."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from sqlalchemy import select

from core.database.session import async_session
from core.events.bus import record_event
from core.logging import get_logger
from core.mcp_hub.models import McpServer
from core.timeutil import naive_local
from plugins.dingtalk.backend import mcp
from plugins.dingtalk.backend.models import DingTalkCalendarSnapshot

log = get_logger(__name__)


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
    return data if isinstance(data, list) else []


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


def _normalize(raw: dict) -> dict | None:
    external_id = str(raw.get("id") or raw.get("iCalUID") or "").strip()
    title = str(raw.get("summary") or raw.get("title") or "").strip()
    start = _event_time(raw.get("start"))
    if not external_id or not title or start is None:
        return None
    end = _event_time(raw.get("end"), fallback_end=True)
    status = "cancelled" if str(raw.get("status") or "").lower() == "cancelled" else "confirmed"
    rooms = [
        str(room.get("roomName") or "").strip()
        for room in (raw.get("meetingRooms") or [])
        if isinstance(room, dict)
    ]
    location = str(raw.get("location") or "").strip() or "、".join(filter(None, rooms)) or None
    organizer = raw.get("organizer") or {}
    online = raw.get("onlineMeetingInfo") or {}
    return {
        "provider": "dingtalk",
        "external_id": external_id,
        "title": title[:200],
        "start": start.isoformat(),
        "end": end.isoformat() if end else None,
        "location": location,
        "status": status,
        "metadata": {
            "organizer": organizer.get("displayName"),
            "attendees": raw.get("attendees") or [],
            "rooms": rooms,
            "meeting_url": online.get("url"),
            "meeting_room_code": (online.get("extraInfo") or {}).get("roomCode"),
            "timezone": (raw.get("start") or {}).get("timeZone"),
            "dingtalk_status": raw.get("status"),
            "ical_uid": raw.get("iCalUID"),
            "series_master_id": raw.get("seriesMasterId"),
        },
    }


def _fingerprint(event: dict) -> str:
    payload = {
        key: event.get(key)
        for key in ("title", "start", "end", "location", "status", "metadata")
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


async def sync_calendar() -> dict:
    days_before = 7
    days_after = 90
    now = datetime.now().astimezone().replace(microsecond=0)
    start = (now - timedelta(days=max(0, days_before))).isoformat()
    end = (now + timedelta(days=max(1, days_after))).isoformat()

    async with async_session() as db:
        user_ids = sorted(set((await db.execute(
            select(McpServer.user_id).where(
                McpServer.owner_plugin == "dingtalk",
                McpServer.enabled == True,  # noqa: E712
            )
        )).scalars().all()))

    stats = {"users": len(user_ids), "events": 0, "unchanged": 0, "errors": 0}
    for user_id in user_ids:
        try:
            payload = await mcp.call(user_id, "list_events", {"start": start, "end": end})
            events = _unwrap(payload, "events")
            if not isinstance(events, list):
                continue
            async with async_session() as db:
                snapshots = {
                    row.external_id: row
                    for row in (await db.execute(
                        select(DingTalkCalendarSnapshot).where(
                            DingTalkCalendarSnapshot.user_id == user_id,
                        )
                    )).scalars().all()
                }
                for raw in events:
                    if not isinstance(raw, dict):
                        continue
                    event = _normalize(raw)
                    if event is None:
                        continue
                    fingerprint = _fingerprint(event)
                    snapshot = snapshots.get(event["external_id"])
                    if snapshot is not None and snapshot.fingerprint == fingerprint:
                        stats["unchanged"] += 1
                        continue
                    event_type = (
                        "calendar.external.delete"
                        if event["status"] == "cancelled"
                        else "calendar.external.upsert"
                    )
                    await record_event(
                        db,
                        user_id,
                        event_type,
                        "calendar",
                        None,
                        f"钉钉日程 · {event['title']}",
                        event,
                    )
                    if snapshot is None:
                        snapshot = DingTalkCalendarSnapshot(
                            user_id=user_id,
                            provider=event["provider"],
                            external_id=event["external_id"],
                            fingerprint=fingerprint,
                        )
                        db.add(snapshot)
                        snapshots[event["external_id"]] = snapshot
                    snapshot.fingerprint = fingerprint
                    snapshot.status = event["status"]
                    stats["events"] += 1
                await db.commit()
        except Exception as exc:
            log.warning(f"[dingtalk.calendar] user {user_id}: {exc}")
            stats["errors"] += 1
    return stats
