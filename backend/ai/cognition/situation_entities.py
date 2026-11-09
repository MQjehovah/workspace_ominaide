"""Resolve entities that are present in the current situation."""

from __future__ import annotations

from sqlalchemy import select

from ai.entities.models import Entity, EntityAlias
from ai.entities.service import normalize_name
from core.database.session import async_session


async def _match_entities(
    db,
    user_id: int,
    text: str | None,
    *,
    types: tuple[str, ...] = ("person", "project", "topic", "organization"),
) -> list[Entity]:
    if not text:
        return []
    normalized = normalize_name(text)
    if not normalized:
        return []
    entities = list((await db.execute(
        select(Entity).where(
            Entity.user_id == user_id,
            Entity.status == "active",
            Entity.type.in_(types),
        )
    )).scalars().all())
    if not entities:
        return []
    by_id = {entity.id: entity for entity in entities}
    matched: dict[int, Entity] = {}
    for entity in entities:
        name = normalize_name(entity.canonical_name)
        if name and name in normalized:
            matched[entity.id] = entity
    aliases = list((await db.execute(
        select(EntityAlias).where(
            EntityAlias.user_id == user_id,
            EntityAlias.entity_id.in_(list(by_id)),
        )
    )).scalars().all())
    for alias in aliases:
        entity = by_id.get(alias.entity_id)
        value = normalize_name(alias.alias)
        if entity is not None and value and value in normalized:
            matched[entity.id] = entity
    return list(matched.values())


def _row(entity: Entity, source_type: str, source_id: int, role: str) -> dict:
    return {
        "entity_id": entity.id,
        "type": entity.type,
        "name": entity.canonical_name,
        "role": role,
        "source_type": source_type,
        "source_id": int(source_id or 0),
        "confidence": 0.8,
    }


async def build_situation_entities(
    user_id: int,
    snapshot: dict | None = None,
) -> list[dict]:
    if snapshot is None:
        from ai.cognition.situation import get_situation

        snapshot = await get_situation(user_id)

    rows: list[dict] = []
    seen: set[tuple] = set()

    def push(entity: Entity, source_type: str, source_id: int, role: str) -> None:
        key = (entity.id, source_type, int(source_id or 0), role)
        if key in seen:
            return
        seen.add(key)
        rows.append(_row(entity, source_type, source_id, role))

    async with async_session() as db:
        for event in snapshot.get("calendar") or []:
            event_id = int(event.get("id") or 0)
            for entity in await _match_entities(db, user_id, str(event.get("title") or "")):
                push(entity, "event", event_id, "about")
            for person in event.get("attendees") or []:
                for entity in await _match_entities(db, user_id, str(person), types=("person",)):
                    push(entity, "event", event_id, "attendee")

        for todo in snapshot.get("todos") or []:
            todo_id = int(todo.get("id") or 0)
            for entity in await _match_entities(
                db, user_id, str(todo.get("title") or "")
            ):
                push(entity, "todo", todo_id, "about")

        recent_mail = (snapshot.get("inbox") or {}).get("recent_mail") or []
        for mail in recent_mail:
            mail_id = int(mail.get("id") or 0)
            for entity in await _match_entities(
                db, user_id, str(mail.get("from") or ""), types=("person",)
            ):
                push(entity, "mail", mail_id, "sender")
            subject = str(mail.get("subject") or "")
            for entity in await _match_entities(db, user_id, subject):
                push(entity, "mail", mail_id, "about")

        for goal in snapshot.get("goals") or []:
            goal_id = int(goal.get("id") or 0)
            for entity in await _match_entities(
                db, user_id, str(goal.get("title") or "")
            ):
                push(entity, "goal", goal_id, "about")

        recent = snapshot.get("recent") or {}
        for group in ("notes", "projects", "files"):
            for item in recent.get(group) or []:
                item_id = int(item.get("id") or 0)
                for entity in await _match_entities(
                    db, user_id, str(item.get("title") or item.get("name") or "")
                ):
                    push(entity, group.rstrip("s"), item_id, "about")

    snapshot["entities"] = rows
    return rows
