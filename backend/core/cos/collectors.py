"""Collect and normalise the signals Chief-of-Staff works from.

Every collector is user-scoped. External MCP sources (DingTalk) are optional:
when no server is configured the collector returns an empty list plus a status
string instead of failing the whole brief.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select

from core.database.session import async_session


def _snippet(value: str | None, size: int = 180) -> str:
    text = " ".join((value or "").split())
    return text[:size]


def _iso(value: datetime | None) -> str | None:
    if not value:
        return None
    # Naive columns hold local wall-clock time; emit an explicit offset so the
    # frontend does not reinterpret them as UTC.
    if value.tzinfo is None:
        value = value.astimezone()
    return value.isoformat()


def _mail_priority(row) -> str:
    if row.important and not row.read:
        return "urgent"
    if row.important:
        return "high"
    if not row.read:
        return "needs_reply"
    return "normal"


async def mail_items(
    user_id: int,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 30,
    unread_only: bool = False,
    query: str | None = None,
    important_only: bool = False,
) -> list[dict]:
    from plugins.mail.backend.models import MailMessage

    async with async_session() as db:
        q = select(MailMessage).where(MailMessage.user_id == user_id)
        if since is not None:
            q = q.where(or_(
                MailMessage.date >= since,
                MailMessage.created_at >= since,
            ))
        if until is not None:
            q = q.where(or_(
                MailMessage.date < until,
                MailMessage.created_at < until,
            ))
        if unread_only:
            q = q.where(MailMessage.read == False)  # noqa: E712
        if important_only:
            q = q.where(MailMessage.important == True)  # noqa: E712
        if query:
            like = f"%{query}%"
            q = q.where(or_(
                MailMessage.subject.ilike(like),
                MailMessage.preview.ilike(like),
                MailMessage.content.ilike(like),
            ))
        q = q.order_by(func.coalesce(MailMessage.date, MailMessage.created_at).desc()).limit(limit)
        rows = list((await db.execute(q)).scalars().all())

    out = []
    for row in rows:
        priority = _mail_priority(row)
        out.append({
            "id": f"mail:{row.id}",
            "source": "mail",
            "source_id": row.id,
            "title": row.subject or "(无主题)",
            "summary": _snippet(row.ai_summary or row.preview or row.content),
            "from": row.from_address or "",
            "time": _iso(row.date or row.created_at),
            "priority": priority,
            "needs_reply": not bool(row.read),
            "link": "/mail",
            "meta": {"important": bool(row.important), "read": bool(row.read)},
        })
    return out


async def todo_items(
    user_id: int,
    *,
    limit: int = 30,
    query: str | None = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
) -> list[dict]:
    from plugins.todo.backend.models import PluginTodoItem

    async with async_session() as db:
        q = select(PluginTodoItem).where(
            PluginTodoItem.user_id == user_id,
            PluginTodoItem.status == "pending",
        )
        if query:
            q = q.where(PluginTodoItem.title.ilike(f"%{query}%"))
        if due_before is not None:
            q = q.where(PluginTodoItem.due_date < due_before)
        if due_after is not None:
            q = q.where(PluginTodoItem.due_date >= due_after)
        q = q.order_by(PluginTodoItem.due_date.is_(None), PluginTodoItem.due_date).limit(limit)
        rows = list((await db.execute(q)).scalars().all())

    now = datetime.now()
    out = []
    for row in rows:
        due = row.due_date
        if due and due < now:
            priority = "urgent"
        elif due and due < now + timedelta(days=1):
            priority = "high"
        else:
            priority = "normal"
        out.append({
            "id": f"todo:{row.id}",
            "source": "todo",
            "source_id": row.id,
            "title": row.title,
            "summary": _snippet(row.description),
            "from": "本地待办",
            "time": _iso(due),
            "priority": priority,
            "needs_reply": False,
            "link": "/dashboard",
            "meta": {"due": _iso(due), "priority": row.priority or 0},
        })
    return out


async def schedule_items(
    user_id: int,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 30,
) -> list[dict]:
    from plugins.schedule.backend.models import Event

    start = start or datetime.now() - timedelta(hours=1)
    end = end or datetime.now() + timedelta(days=1)
    async with async_session() as db:
        rows = list((await db.execute(
            select(Event).where(
                Event.user_id == user_id,
                Event.start_time >= start,
                Event.start_time < end,
            ).order_by(Event.start_time).limit(limit)
        )).scalars().all())

    now = datetime.now()
    out = []
    for row in rows:
        priority = "urgent" if now <= row.start_time <= now + timedelta(hours=2) else "normal"
        out.append({
            "id": f"schedule:{row.id}",
            "source": "schedule",
            "source_id": row.id,
            "title": row.title,
            "summary": _snippet(row.notes),
            "from": "日程",
            "time": _iso(row.start_time),
            "priority": priority,
            "needs_reply": False,
            "link": "/schedule",
            "meta": {"end": _iso(row.end_time)},
        })
    return out


async def source_items(
    user_id: int,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 20,
    query: str | None = None,
) -> list[dict]:
    from plugins.sources.backend.models import ContentItem, ContentSource

    async with async_session() as db:
        q = (
            select(ContentItem)
            .join(ContentSource, ContentItem.source_id == ContentSource.id)
            .where(ContentSource.user_id == user_id)
        )
        if since is not None:
            q = q.where(or_(ContentItem.published >= since, ContentItem.created_at >= since))
        if until is not None:
            q = q.where(or_(ContentItem.published < until, ContentItem.created_at < until))
        if query:
            like = f"%{query}%"
            q = q.where(or_(ContentItem.title.ilike(like), ContentItem.summary.ilike(like)))
        q = q.order_by(func.coalesce(ContentItem.published, ContentItem.created_at).desc()).limit(limit)
        rows = list((await db.execute(q)).scalars().all())

    return [
        {
            "id": f"sources:{row.id}",
            "source": "sources",
            "source_id": row.id,
            "title": row.title,
            "summary": _snippet(row.summary or row.content),
            "from": row.author or "资讯",
            "time": _iso(row.published or row.created_at),
            "priority": "normal",
            "needs_reply": False,
            "link": "/sources",
            "meta": {"read": bool(row.read), "url": row.link},
        }
        for row in rows
    ]


def _walk_dicts(value, out: list[dict], depth: int = 0) -> None:
    if depth > 6:
        return
    if isinstance(value, dict):
        out.append(value)
        for child in value.values():
            _walk_dicts(child, out, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _walk_dicts(child, out, depth + 1)


def _first(mapping: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return ""


def _parse_mcp_data(response) -> dict | None:
    if response is None or response.isError or not response.content:
        return None
    text = response.content[0].text or ""
    try:
        payload = json.loads(text)
    except Exception:
        return None
    if isinstance(payload, dict) and payload.get("ok") is False:
        return None
    return payload.get("data") if isinstance(payload, dict) and "data" in payload else payload


async def _dingtalk_server(user_id: int):
    from core.mcp_hub.models import McpServer

    async with async_session() as db:
        return (await db.execute(
            select(McpServer).where(
                McpServer.user_id == user_id,
                McpServer.enabled == True,  # noqa: E712
                or_(
                    McpServer.slug == "dingtalk",
                    McpServer.slug.like("dingtalk%"),
                    McpServer.name.ilike("%钉钉%"),
                ),
            ).order_by(McpServer.id).limit(1)
        )).scalar_one_or_none()


def _normalise_dingtalk_time(value) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        stamp = int(raw)
        if stamp > 10**12:
            stamp //= 1000
        try:
            return datetime.fromtimestamp(stamp).isoformat()
        except Exception:
            return None
    try:
        from core.timeutil import parse_datetime

        return parse_datetime(raw).isoformat()
    except Exception:
        return None


_DINGTALK_TITLE_KEYS = (
    "conversationTitle", "conversationName", "chatName", "groupName",
    "title", "name",
)
_DINGTALK_TEXT_KEYS = (
    "lastMessage", "text", "content", "summary", "message", "preview",
)
_DINGTALK_TIME_KEYS = ("lastMessageTime", "lastMsgTime", "createTime", "time", "timestamp")
_DINGTALK_ID_KEYS = ("openConversationId", "conversationId", "chatId", "openId")


def normalise_dingtalk_payload(data, limit: int = 15) -> list[dict]:
    """Turn an unknown dws payload into inbox items.

    Only dicts that actually carry message text become items; nested objects
    such as ``{"sender": {"name": "张三"}}`` are ignored instead of appearing
    as fake conversations.
    """
    candidates: list[dict] = []
    _walk_dicts(data, candidates)
    items: list[dict] = []
    seen: set[str] = set()
    for row in candidates:
        text = _first(row, _DINGTALK_TEXT_KEYS)
        if not text:
            continue
        raw_title = _first(row, _DINGTALK_TITLE_KEYS)
        source_id = _first(row, _DINGTALK_ID_KEYS)
        if not raw_title and not source_id:
            continue
        title = raw_title or "钉钉消息"
        key = f"{title}|{text}"
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "id": f"dingtalk:{source_id or len(items)}",
            "source": "dingtalk",
            "source_id": None,
            "title": title,
            "summary": _snippet(text),
            "from": title,
            "time": _normalise_dingtalk_time(_first(row, _DINGTALK_TIME_KEYS)),
            "priority": "needs_reply",
            "needs_reply": True,
            "link": "/mcp",
            "meta": {"conversation_id": source_id or None},
        })
        if len(items) >= limit:
            break
    return items


async def dingtalk_items(
    user_id: int,
    *,
    query: str | None = None,
    limit: int = 15,
) -> tuple[list[dict], str]:
    """Return normalised DingTalk items and a source status string."""
    server = await _dingtalk_server(user_id)
    if server is None:
        return [], "not_configured"

    from core.mcp_hub.hub import mcp_hub

    tool = "search_messages" if query else "list_unread"
    args = {"query": query, "limit": limit} if query else {"count": limit}
    try:
        response = await mcp_hub.call_external(server.id, tool, user_id, args)
    except Exception:
        return [], "error"
    data = _parse_mcp_data(response)
    if data is None:
        return [], "error"

    items = normalise_dingtalk_payload(data, limit)
    return items, "ok" if items else "empty"


def group_items(items: list[dict]) -> dict[str, list[dict]]:
    """Split triage items into actionable buckets; each item lands in one."""
    groups: dict[str, list[dict]] = {
        "urgent": [],
        "needs_reply": [],
        "today": [],
        "fyi": [],
    }
    for item in items:
        if item["priority"] == "urgent":
            groups["urgent"].append(item)
        elif item["needs_reply"]:
            groups["needs_reply"].append(item)
        elif item["priority"] == "high" or item["source"] in ("schedule", "todo"):
            groups["today"].append(item)
        else:
            groups["fyi"].append(item)
    for key, bucket in groups.items():
        bucket.sort(key=lambda x: x.get("time") or "", reverse=(key != "today"))
    return groups
