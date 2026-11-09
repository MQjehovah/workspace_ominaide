"""Resolve entities that are present in the current situation."""

from __future__ import annotations

from sqlalchemy import select

from ai.entities.models import Entity, EntityAlias
from ai.entities.service import normalize_name
from core.database.session import async_session


def _int_id(value) -> int:
    if isinstance(value, int):
        return value
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return int(digits) if digits else 0


class _EntityIndex:
    def __init__(self, entities: list[Entity], aliases: list[EntityAlias]):
        self.entities = entities
        self.by_id = {entity.id: entity for entity in entities}
        self.aliases = aliases
        self._cache: dict[tuple[str, tuple[str, ...]], list[Entity]] = {}

    def match(
        self,
        text: str | None,
        types: tuple[str, ...] = ("person", "project", "topic", "organization"),
    ) -> list[Entity]:
        if not text:
            return []
        normalized = normalize_name(text)
        if not normalized:
            return []
        cache_key = (normalized, types)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        matched: dict[int, Entity] = {}
        for entity in self.entities:
            if entity.type not in types:
                continue
            name = normalize_name(entity.canonical_name)
            if name and name in normalized:
                matched[entity.id] = entity
        for alias in self.aliases:
            entity = self.by_id.get(alias.entity_id)
            if entity is None or entity.type not in types:
                continue
            value = normalize_name(alias.alias)
            if value and value in normalized:
                matched[entity.id] = entity
        result = list(matched.values())
        self._cache[cache_key] = result
        return result


def _row(entity: Entity, source_type: str, source_id: int, role: str) -> dict:
    return {
        "entity_id": entity.id,
        "type": entity.type,
        "name": entity.canonical_name,
        "role": role,
        "source_type": source_type,
        "source_id": _int_id(source_id),
        "confidence": 0.8,
    }


async def build_situation_entities(
    user_id: int,
    snapshot: dict | None = None,
) -> list[dict]:
    if snapshot is None:
        from ai.cognition.situation import get_situation

        snapshot = await get_situation(user_id)

    async with async_session() as db:
        entities = list((await db.execute(
            select(Entity).where(
                Entity.user_id == user_id,
                Entity.status == "active",
            )
        )).scalars().all())
        aliases = []
        if entities:
            aliases = list((await db.execute(
                select(EntityAlias).where(
                    EntityAlias.user_id == user_id,
                    EntityAlias.entity_id.in_([entity.id for entity in entities]),
                )
            )).scalars().all())
    index = _EntityIndex(entities, aliases)

    rows: list[dict] = []
    seen: set[tuple] = set()

    def push(entity: Entity, source_type: str, source_id: int, role: str) -> None:
        key = (entity.id, source_type, _int_id(source_id), role)
        if key in seen:
            return
        seen.add(key)
        rows.append(_row(entity, source_type, source_id, role))

    for event in snapshot.get("calendar") or []:
        event_id = _int_id(event.get("id"))
        for entity in index.match(str(event.get("title") or "")):
            push(entity, "event", event_id, "about")
        for person in event.get("attendees") or []:
            for entity in index.match(str(person), types=("person",)):
                push(entity, "event", event_id, "attendee")

    for todo in snapshot.get("todos") or []:
        todo_id = _int_id(todo.get("id"))
        for entity in index.match(str(todo.get("title") or "")):
            push(entity, "todo", todo_id, "about")

    recent_mail = (snapshot.get("inbox") or {}).get("recent_mail") or []
    for mail in recent_mail:
        mail_id = _int_id(mail.get("id"))
        for entity in index.match(
            str(mail.get("from") or mail.get("from_address") or ""),
            types=("person",),
        ):
            push(entity, "mail", mail_id, "sender")
        for entity in index.match(
            str(mail.get("subject") or mail.get("title") or "")
        ):
            push(entity, "mail", mail_id, "about")

    for goal in snapshot.get("goals") or []:
        goal_id = _int_id(goal.get("id"))
        for entity in index.match(str(goal.get("title") or "")):
            push(entity, "goal", goal_id, "about")

    recent = snapshot.get("recent") or {}
    for group in ("notes", "projects", "files"):
        for item in recent.get(group) or []:
            item_id = _int_id(item.get("id"))
            for entity in index.match(
                str(item.get("title") or item.get("name") or "")
            ):
                push(entity, group.rstrip("s"), item_id, "about")

    snapshot["entities"] = rows
    return rows
