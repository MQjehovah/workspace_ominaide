"""Load the text behind an entity mention so relations can be extracted."""

from __future__ import annotations

import json


def _clip(text, limit: int = 4000) -> str:
    value = " ".join(str(text or "").split())
    return value[:limit]


async def load_source_text(
    db,
    user_id: int,
    source_type: str,
    source_id: int,
    *,
    limit: int = 4000,
) -> str:
    kind = (source_type or "").rstrip("s")
    if kind == "note":
        from plugins.notes.backend.models import PluginNote

        row = await db.get(PluginNote, source_id)
        if row is not None and row.user_id == user_id:
            return _clip(f"{row.title or ''}\n{row.content or ''}", limit)
    if kind == "mail":
        from plugins.mail.backend.models import MailMessage

        row = await db.get(MailMessage, source_id)
        if row is not None and row.user_id == user_id:
            return _clip(
                f"{row.subject or ''}\n{row.from_address or ''}\n"
                f"{row.content or row.preview or ''}",
                limit,
            )
    if kind == "event":
        from plugins.schedule.backend.models import Event

        row = await db.get(Event, source_id)
        if row is not None and row.user_id == user_id:
            return _clip(
                f"{row.title or ''}\n{row.location or ''}\n{row.notes or ''}",
                limit,
            )
    if kind == "todo":
        from plugins.todo.backend.models import PluginTodoItem

        row = await db.get(PluginTodoItem, source_id)
        if row is not None and row.user_id == user_id:
            return _clip(f"{row.title or ''}\n{row.description or ''}", limit)
    if kind == "meeting":
        from plugins.meetings.backend.models import MeetingMinutesJob

        row = await db.get(MeetingMinutesJob, source_id)
        if row is not None and row.user_id == user_id:
            minutes = row.minutes if isinstance(row.minutes, dict) else {}
            return _clip(
                f"{row.title or ''}\n{row.transcript or ''}\n"
                f"{minutes.get('summary') or ''}",
                limit,
            )
    if kind == "memory":
        from ai.memory.models import MemoryRecord

        row = await db.get(MemoryRecord, source_id)
        if row is not None and row.user_id == user_id:
            return _clip(row.content or "", limit)
    if kind == "project":
        from app.objects.models import BusinessComment
        from plugins.projects.backend.models import Project
        from sqlalchemy import select

        row = await db.get(Project, source_id)
        if row is not None and row.user_id == user_id:
            comments = list((await db.execute(
                select(BusinessComment)
                .where(
                    BusinessComment.user_id == user_id,
                    BusinessComment.object_type == "project",
                    BusinessComment.object_id == source_id,
                    BusinessComment.deleted_at.is_(None),
                )
                .order_by(BusinessComment.id.desc())
                .limit(10)
            )).scalars().all())
            text = "\n".join(
                f"{item.title or ''}\n{item.content or ''}" for item in comments
            )
            return _clip(
                f"{row.name or ''}\n{row.description or ''}\n{text}", limit
            )
    if kind in ("source_item", "source", "article"):
        from plugins.sources.backend.models import ContentItem

        row = await db.get(ContentItem, source_id)
        if row is not None:
            return _clip(
                f"{row.title or ''}\n{row.summary or ''}\n{row.content or ''}",
                limit,
            )
    if kind in ("session", "chat"):
        from core.sessions.models import SessionMessage
        from sqlalchemy import select

        rows = list((await db.execute(
            select(SessionMessage)
            .where(
                SessionMessage.user_id == user_id,
                SessionMessage.session_id == str(source_id),
            )
            .order_by(SessionMessage.id.desc())
            .limit(12)
        )).scalars().all())
        text = "\n".join(str(item.content or "") for item in reversed(rows))
        return _clip(text, limit)
    return ""
