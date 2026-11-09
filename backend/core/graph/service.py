from __future__ import annotations

from sqlalchemy import or_, select

from core.database.session import async_session
from core.graph.models import EntityLink


async def create_link(
    user_id: int,
    *,
    from_type: str,
    from_id: int,
    to_type: str,
    to_id: int,
    relation: str = "related",
    confidence: float = 1.0,
    source: str | None = None,
    meta: dict | None = None,
) -> dict:
    async with async_session() as db:
        existing = (
            await db.execute(
                select(EntityLink).where(
                    EntityLink.user_id == user_id,
                    EntityLink.from_type == from_type,
                    EntityLink.from_id == from_id,
                    EntityLink.to_type == to_type,
                    EntityLink.to_id == to_id,
                    EntityLink.relation == relation,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = EntityLink(
                user_id=user_id,
                from_type=from_type,
                from_id=from_id,
                to_type=to_type,
                to_id=to_id,
                relation=relation,
                confidence=confidence,
                source=source,
                meta=meta,
            )
            db.add(existing)
            await db.commit()
            await db.refresh(existing)
        return _link_out(existing)


def _link_out(link: EntityLink) -> dict:
    return {
        "id": link.id,
        "from_type": link.from_type,
        "from_id": link.from_id,
        "to_type": link.to_type,
        "to_id": link.to_id,
        "relation": link.relation,
        "confidence": link.confidence,
        "source": link.source,
        "meta": link.meta,
    }


async def object_title(user_id: int, object_type: str, object_id: int) -> dict | None:
    async with async_session() as db:
        if object_type == "note":
            from plugins.notes.backend.models import PluginNote

            row = await db.get(PluginNote, object_id)
            return (
                {"type": object_type, "id": object_id, "title": row.title, "link": "/notes"}
                if row and row.user_id == user_id
                else None
            )
        if object_type == "file":
            from plugins.files.backend.models import File

            row = await db.get(File, object_id)
            return (
                {
                    "type": object_type,
                    "id": object_id,
                    "title": row.original_name,
                    "link": "/files",
                }
                if row and row.user_id == user_id
                else None
            )
        if object_type == "mail":
            from plugins.mail.backend.models import MailMessage

            row = await db.get(MailMessage, object_id)
            return (
                {"type": object_type, "id": object_id, "title": row.subject, "link": "/mail"}
                if row and row.user_id == user_id
                else None
            )
        if object_type == "event":
            from plugins.schedule.backend.models import Event

            row = await db.get(Event, object_id)
            return (
                {"type": object_type, "id": object_id, "title": row.title, "link": "/schedule"}
                if row and row.user_id == user_id
                else None
            )
        if object_type == "todo":
            from plugins.todo.backend.models import PluginTodoItem

            row = await db.get(PluginTodoItem, object_id)
            return (
                {"type": object_type, "id": object_id, "title": row.title, "link": "/dashboard"}
                if row and row.user_id == user_id
                else None
            )
        if object_type == "project":
            from plugins.projects.backend.models import Project

            row = await db.get(Project, object_id)
            return (
                {"type": object_type, "id": object_id, "title": row.name, "link": "/projects"}
                if row and row.user_id == user_id
                else None
            )
        if object_type == "meeting":
            from plugins.meetings.backend.models import MeetingMinutesJob

            row = await db.get(MeetingMinutesJob, object_id)
            return (
                {"type": object_type, "id": object_id, "title": row.title, "link": "/notes"}
                if row and row.user_id == user_id
                else None
            )
    return None


async def related(user_id: int, object_type: str, object_id: int) -> list[dict]:
    async with async_session() as db:
        links = (
            await db.execute(
                select(EntityLink).where(
                    EntityLink.user_id == user_id,
                    or_(
                        (EntityLink.from_type == object_type)
                        & (EntityLink.from_id == object_id),
                        (EntityLink.to_type == object_type)
                        & (EntityLink.to_id == object_id),
                    ),
                )
            )
        ).scalars().all()
    out = []
    for link in links:
        if link.from_type == object_type and link.from_id == object_id:
            other_type, other_id = link.to_type, link.to_id
        else:
            other_type, other_id = link.from_type, link.from_id
        node = await object_title(user_id, other_type, other_id)
        if node is not None:
            node["relation"] = link.relation
            node["confidence"] = link.confidence
            out.append(node)
    return out


def _snippet(value, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


async def build_context(
    user_id: int,
    query: str,
    *,
    object_type: str | None = None,
    object_id: int | None = None,
    limit: int = 6,
) -> dict:
    like = f"%{query.strip()}%"
    items: list[dict] = []
    if not query.strip() and not (object_type and object_id):
        return {"query": query, "items": [], "count": 0, "related": []}

    async with async_session() as db:
        if query.strip():
            from plugins.notes.backend.models import PluginNote
            from plugins.files.backend.models import File
            from plugins.mail.backend.models import MailMessage
            from plugins.schedule.backend.models import Event
            from plugins.todo.backend.models import PluginTodoItem
            from plugins.meetings.backend.models import MeetingMinutesJob

            notes = (
                await db.execute(
                    select(PluginNote)
                    .where(
                        PluginNote.user_id == user_id,
                        PluginNote.is_folder == 0,
                        or_(
                            PluginNote.title.ilike(like),
                            PluginNote.content.ilike(like),
                        ),
                    )
                    .limit(limit)
                )
            ).scalars().all()
            for row in notes:
                items.append(
                    {
                        "type": "note",
                        "id": row.id,
                        "title": row.title,
                        "snippet": _snippet(row.content),
                        "citation": f"note:{row.id}",
                    }
                )

            files = (
                await db.execute(
                    select(File)
                    .where(
                        File.user_id == user_id,
                        File.status == "active",
                        File.original_name.ilike(like),
                    )
                    .limit(limit)
                )
            ).scalars().all()
            for row in files:
                items.append(
                    {
                        "type": "file",
                        "id": row.id,
                        "title": row.original_name,
                        "snippet": row.mime_type or "",
                        "citation": f"file:{row.id}",
                    }
                )

            mail = (
                await db.execute(
                    select(MailMessage)
                    .where(
                        MailMessage.user_id == user_id,
                        or_(
                            MailMessage.subject.ilike(like),
                            MailMessage.preview.ilike(like),
                            MailMessage.from_address.ilike(like),
                        ),
                    )
                    .order_by(MailMessage.date.desc())
                    .limit(limit)
                )
            ).scalars().all()
            for row in mail:
                items.append(
                    {
                        "type": "mail",
                        "id": row.id,
                        "title": row.subject or "(无主题)",
                        "snippet": _snippet(row.preview or row.content),
                        "citation": f"mail:{row.id}",
                    }
                )

            events = (
                await db.execute(
                    select(Event)
                    .where(
                        Event.user_id == user_id,
                        or_(Event.title.ilike(like), Event.notes.ilike(like)),
                    )
                    .limit(limit)
                )
            ).scalars().all()
            for row in events:
                items.append(
                    {
                        "type": "event",
                        "id": row.id,
                        "title": row.title,
                        "snippet": _snippet(row.notes),
                        "citation": f"event:{row.id}",
                    }
                )

            todos = (
                await db.execute(
                    select(PluginTodoItem)
                    .where(
                        PluginTodoItem.user_id == user_id,
                        PluginTodoItem.title.ilike(like),
                    )
                    .limit(limit)
                )
            ).scalars().all()
            for row in todos:
                items.append(
                    {
                        "type": "todo",
                        "id": row.id,
                        "title": row.title,
                        "snippet": _snippet(row.description),
                        "citation": f"todo:{row.id}",
                    }
                )

            meetings = (
                await db.execute(
                    select(MeetingMinutesJob)
                    .where(
                        MeetingMinutesJob.user_id == user_id,
                        MeetingMinutesJob.status == "done",
                        or_(
                            MeetingMinutesJob.title.ilike(like),
                            MeetingMinutesJob.transcript.ilike(like),
                        ),
                    )
                    .limit(limit)
                )
            ).scalars().all()
            for row in meetings:
                items.append(
                    {
                        "type": "meeting",
                        "id": row.id,
                        "title": row.title,
                        "snippet": _snippet(
                            (row.minutes or {}).get("summary") if row.minutes else ""
                        ),
                        "citation": f"meeting:{row.id}",
                    }
                )

    related_nodes = []
    if object_type and object_id is not None:
        related_nodes = await related(user_id, object_type, object_id)
        items = related_nodes + items
    return {
        "query": query,
        "items": items,
        "count": len(items),
        "related": related_nodes,
    }
