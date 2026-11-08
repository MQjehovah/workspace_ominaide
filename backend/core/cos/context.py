"""Shared user context for daily briefs and activity analysis."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from core.cos import collectors
from core.database.session import async_session


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
    """Collect the context shared by the hourly brief and activity analysis."""
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

    events = await collectors.schedule_items(
        user_id, start=event_start, end=event_end, limit=12,
    )
    todos = await collectors.todo_items(user_id, limit=12)
    mail = await collectors.mail_items(
        user_id,
        since=mail_since,
        until=mail_until,
        limit=8,
        unread_only=True,
    )
    news = await collectors.source_items(
        user_id,
        since=news_since,
        until=news_until,
        limit=5,
    )
    dingtalk, dingtalk_status = await collectors.dingtalk_items(user_id, limit=8)

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
