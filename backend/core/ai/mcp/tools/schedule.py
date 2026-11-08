"""Schedule-specific agent tools with DingTalk write-through."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import select

from core.ai.mcp.core import MCPCallResponse, MCPContent, MCPTool


def _ok(value) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=json.dumps(
        {"ok": True, "data": value}, ensure_ascii=False
    ))])


def _err(message: str) -> MCPCallResponse:
    return MCPCallResponse(
        content=[MCPContent(text=json.dumps({"ok": False, "error": message}, ensure_ascii=False))],
        isError=True,
    )


def _confirmation(message: str, **fields) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=json.dumps({
        "confirmation_required": True,
        "message": message,
        **fields,
    }, ensure_ascii=False))])


async def find_schedule_events(user_id: int, args: dict) -> MCPCallResponse:
    from core.database.session import async_session
    from core.objects.registry import resolve_object
    from core.timeutil import naive_local
    from plugins.schedule.backend.models import Event

    query = str(args.get("query") or "").strip()
    source = str(args.get("source") or "").strip()
    limit = max(1, min(int(args.get("limit") or 20), 50))
    try:
        start = naive_local(args.get("start")) if args.get("start") else None
        end = naive_local(args.get("end")) if args.get("end") else None
    except Exception:
        return _err("start/end 不是合法时间")

    async with async_session() as db:
        q = select(Event).where(Event.user_id == user_id)
        if query:
            q = q.where(Event.title.ilike(f"%{query}%"))
        if source:
            q = q.where(Event.source == source)
        if start:
            q = q.where(Event.start_time >= start)
        if end:
            q = q.where(Event.start_time <= end)
        q = q.order_by(Event.start_time).limit(limit)
        rows = list((await db.execute(q)).scalars().all())

    items = []
    for row in rows:
        item = await resolve_object(user_id, "schedule_event", row.id)
        if item:
            items.append(item)
    return _ok({"items": items})


async def get_schedule_event(user_id: int, args: dict) -> MCPCallResponse:
    from core.objects.registry import resolve_object

    try:
        event_id = int(args.get("event_id"))
    except (TypeError, ValueError):
        return _err("event_id 必填")
    item = await resolve_object(user_id, "schedule_event", event_id)
    if item is None:
        return _err("日程不存在")
    return _ok(item)


async def update_schedule_event(user_id: int, args: dict) -> MCPCallResponse:
    from core.database.session import async_session
    from core.timeutil import naive_local, parse_datetime
    from plugins.schedule.backend.models import Event
    from plugins.schedule.backend.schemas import EventUpdate
    from plugins.schedule.backend.service import update_event

    try:
        event_id = int(args.get("event_id"))
    except (TypeError, ValueError):
        return _err("event_id 必填")

    async with async_session() as db:
        event = (await db.execute(
            select(Event).where(Event.id == event_id, Event.user_id == user_id)
        )).scalar_one_or_none()
        if event is None:
            return _err("日程不存在")
        source = event.source or "manual"
        external_id = event.external_id

    start_raw = args.get("start_time")
    end_raw = args.get("end_time")
    start = parse_datetime(start_raw) if start_raw else None
    end = parse_datetime(end_raw) if end_raw else None
    if bool(start) != bool(end):
        return _err("start_time 和 end_time 必须同时提供")
    payload_data: dict = {}
    if args.get("title") is not None:
        payload_data["title"] = str(args.get("title")).strip()
    if args.get("notes") is not None:
        payload_data["notes"] = args.get("notes")
    if args.get("location") is not None:
        payload_data["location"] = str(args.get("location")).strip()
    if args.get("remind_before") is not None:
        payload_data["remind_before"] = int(args.get("remind_before"))
    if start and end:
        payload_data["start_time"] = start
        payload_data["end_time"] = end
    if not payload_data:
        return _err("至少提供一项要修改的内容")
    if not args.get("confirmed"):
        return _confirmation(
            "修改日程需要用户确认；确认后以 confirmed=true 重新调用。",
            event_id=event_id,
            source=source,
        )

    # DingTalk is the source of truth for mirrored events.
    if source == "dingtalk" and (start or payload_data.get("title") or payload_data.get("location")):
        if not external_id:
            return _err("该钉钉日程缺少 external_id，请先重新同步")
        from plugins.dingtalk.backend import api as dingtalk_api

        patch = {
            "title": payload_data.get("title"),
            "location": payload_data.get("location"),
        }
        if start and end:
            patch["start"] = start.astimezone().isoformat()
            patch["end"] = end.astimezone().isoformat()
        try:
            await dingtalk_api.update_calendar_event(user_id, external_id, patch)
        except Exception as e:
            return _err(f"钉钉日程更新失败: {e}")

    payload = EventUpdate(**payload_data)
    async with async_session() as db:
        row = await update_event(db, user_id, event_id, payload)
        if row is None:
            return _err("日程不存在")
        await db.commit()
        result = {
            "event_id": row.id,
            "title": row.title,
            "start_time": row.start_time.isoformat() if row.start_time else None,
            "end_time": row.end_time.isoformat() if row.end_time else None,
            "source": row.source,
            "status": row.status,
        }
    return _ok(result)


async def cancel_schedule_event(user_id: int, args: dict) -> MCPCallResponse:
    from core.database.session import async_session
    from plugins.schedule.backend.models import Event

    try:
        event_id = int(args.get("event_id"))
    except (TypeError, ValueError):
        return _err("event_id 必填")

    async with async_session() as db:
        event = (await db.execute(
            select(Event).where(Event.id == event_id, Event.user_id == user_id)
        )).scalar_one_or_none()
        if event is None:
            return _err("日程不存在")
        source = event.source or "manual"
        external_id = event.external_id
        title = event.title

    if not args.get("confirmed"):
        return _confirmation(
            "取消日程会删除/取消该日程，需要用户确认；确认后以 confirmed=true 重新调用。",
            event_id=event_id,
            title=title,
            source=source,
        )

    if source == "dingtalk" and external_id:
        from plugins.dingtalk.backend import api as dingtalk_api

        try:
            await dingtalk_api.cancel_calendar_event(user_id, external_id)
        except Exception as e:
            return _err(f"钉钉日程取消失败: {e}")

    async with async_session() as db:
        event = (await db.execute(
            select(Event).where(Event.id == event_id, Event.user_id == user_id)
        )).scalar_one_or_none()
        if event is None:
            return _err("日程不存在")
        event.status = "cancelled"
        await db.commit()
    return _ok({"event_id": event_id, "status": "cancelled"})


TOOLS = [
    (
        MCPTool(
            name="find_schedule_events",
            description="按标题、日期范围或来源查找日程，返回统一对象引用和编号。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "标题关键词，可选"},
                    "start": {"type": "string", "description": "开始时间 ISO，可选"},
                    "end": {"type": "string", "description": "结束时间 ISO，可选"},
                    "source": {"type": "string", "description": "dingtalk/agent/manual，可选"},
                    "limit": {"type": "integer", "description": "最多返回数量，默认 20"},
                },
            },
        ),
        find_schedule_events,
    ),
    (
        MCPTool(
            name="get_schedule_event",
            description="读取一个日程的完整信息，包括来源、地点和钉钉元数据。",
            inputSchema={
                "type": "object",
                "properties": {"event_id": {"type": "integer"}},
                "required": ["event_id"],
            },
        ),
        get_schedule_event,
    ),
    (
        MCPTool(
            name="update_schedule_event",
            description=(
                "修改日程标题、时间、地点、备注或提醒。钉钉同步的日程会先回写钉钉。"
                "需要用户确认后设置 confirmed=true。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "event_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "start_time": {"type": "string", "description": "ISO 时间，与 end_time 同时提供"},
                    "end_time": {"type": "string", "description": "ISO 时间，与 start_time 同时提供"},
                    "notes": {"type": "string", "description": "本地备注，不会写回钉钉"},
                    "location": {"type": "string"},
                    "remind_before": {"type": "integer"},
                    "confirmed": {"type": "boolean"},
                },
                "required": ["event_id"],
            },
        ),
        update_schedule_event,
    ),
    (
        MCPTool(
            name="cancel_schedule_event",
            description="取消日程。钉钉日程会先取消钉钉侧，再标记本地状态。需要 confirmed=true。",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_id": {"type": "integer"},
                    "confirmed": {"type": "boolean"},
                },
                "required": ["event_id"],
            },
        ),
        cancel_schedule_event,
    ),
]
