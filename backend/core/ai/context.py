"""Read-only context assembly for AI scenarios.

Scenarios such as the daily brief, weekly review, meeting prep and activity
insights all read the same cross-source snapshot. This module keeps that
assembly in one place inside the AI domain; it is not a shared platform layer.
"""

from __future__ import annotations

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


def _dingtalk_summary(content: str, query: str | None, size: int = 180) -> str:
    lines = [line.strip() for line in (content or "").splitlines() if line.strip()]
    if query:
        needle = query.lower()
        matched = [line for line in lines if needle in line.lower()]
        if matched:
            lines = matched
    return _snippet(" ".join(lines[-2:]), size)


async def dingtalk_items(
    user_id: int,
    *,
    query: str | None = None,
    limit: int = 15,
) -> tuple[list[dict], str]:
    """Read DingTalk conversations cached by the plugin sync."""
    from core.activities.models import UserActivity

    # The scheduler syncs once a day; keep the latest day (two days of slack)
    # so a missed sync does not empty the context.
    since = datetime.now() - timedelta(days=7 if query else 2)
    async with async_session() as db:
        rows = list((await db.execute(
            select(UserActivity)
            .where(
                UserActivity.user_id == user_id,
                UserActivity.event_type == "dingtalk.conversation",
                UserActivity.created_at >= since,
            )
            .order_by(UserActivity.created_at.desc())
            .limit(max(limit * 3, 30))
        )).scalars().all())

    items: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        details = row.details if isinstance(row.details, dict) else {}
        conv_id = str(details.get("conversation_id") or "")
        conv_name = str(details.get("conversation") or conv_id or "钉钉会话")
        content = str(details.get("content") or "")
        if query:
            needle = query.lower()
            if needle not in conv_name.lower() and needle not in content.lower():
                continue
        key = conv_id or str(row.id)
        if key in seen:
            continue
        seen.add(key)
        try:
            unread = max(0, int(details.get("unread_count") or 0))
        except (TypeError, ValueError):
            unread = 0
        items.append({
            "id": f"dingtalk:{conv_id or row.id}",
            "source": "dingtalk",
            "source_id": None,
            "title": conv_name,
            "summary": _dingtalk_summary(content, query),
            "from": conv_name,
            "time": _iso(row.created_at),
            "priority": "needs_reply" if unread else "fyi",
            "needs_reply": bool(unread),
            "link": "/mcp",
            "meta": {
                "conversation_id": conv_id or None,
                "day": details.get("day"),
                "unread_count": unread,
                "read": unread == 0,
            },
        })
        if len(items) >= limit:
            break
    return items, ("cached" if items else "empty")


async def _recent_notes(user_id: int, limit: int = 3) -> list[dict]:
    from plugins.notes.backend.models import PluginNote

    async with async_session() as db:
        rows = list((await db.execute(
            select(PluginNote)
            .where(
                PluginNote.user_id == user_id,
                PluginNote.is_folder == 0,
            )
            .order_by(PluginNote.updated_at.desc())
            .limit(limit)
        )).scalars().all())
    return [
        {
            "title": row.title,
            "updated": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]


async def _recent_files(user_id: int, limit: int = 3) -> list[dict]:
    from plugins.files.backend.models import File

    async with async_session() as db:
        rows = list((await db.execute(
            select(File)
            .where(
                File.user_id == user_id,
                File.is_folder == False,  # noqa: E712
                File.status == "active",
            )
            .order_by(File.created_at.desc())
            .limit(limit)
        )).scalars().all())
    return [
        {
            "name": row.original_name,
            "created": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


async def _recent_projects(user_id: int, limit: int = 3) -> list[dict]:
    from plugins.projects.backend.models import Project

    async with async_session() as db:
        rows = list((await db.execute(
            select(Project)
            .where(Project.user_id == user_id)
            .order_by(Project.updated_at.desc())
            .limit(limit)
        )).scalars().all())
    return [
        {
            "name": row.name,
            "updated": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]


async def _memory_lines(user_id: int, limit: int = 5) -> list[str]:
    try:
        from core.memory_service import list_records

        records = await list_records(user_id, "", limit)
        return [row.content for row in records[:limit]]
    except Exception:
        return []


async def build_context(
    user_id: int,
    *,
    now: datetime | None = None,
    day: datetime | None = None,
    horizon_hours: int = 48,
) -> dict:
    """Collect the context shared by AI scenarios."""
    now = now or datetime.now()
    if day is None:
        event_start = now - timedelta(minutes=30)
        event_end = now + timedelta(hours=max(1, horizon_hours))
        mail_since = now - timedelta(days=3)
        mail_until = None
        news_since = now - timedelta(hours=36)
        news_until = None
    else:
        event_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        event_end = event_start + timedelta(days=1)
        mail_since = event_start
        mail_until = event_end
        news_since = event_start
        news_until = event_end

    events = await schedule_items(
        user_id, start=event_start, end=event_end, limit=12,
    )
    todos = await todo_items(user_id, limit=12)
    mail = await mail_items(
        user_id,
        since=mail_since,
        until=mail_until,
        limit=8,
        unread_only=True,
    )
    news = await source_items(
        user_id,
        since=news_since,
        until=news_until,
        limit=5,
    )
    dingtalk, dingtalk_status = await dingtalk_items(user_id, limit=8)

    return {
        "now": now.isoformat(timespec="minutes"),
        "events": events,
        "todos": todos,
        "unread_mail": mail,
        "news": news,
        "dingtalk": dingtalk,
        "dingtalk_status": dingtalk_status,
        "recent_notes": await _recent_notes(user_id),
        "recent_files": await _recent_files(user_id),
        "recent_projects": await _recent_projects(user_id),
        "memory": await _memory_lines(user_id),
    }
