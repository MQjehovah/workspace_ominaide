"""Extract entity seeds and mentions from profiles and memories."""

from __future__ import annotations

import json

from sqlalchemy import func, select

from ai.entities.models import Entity, EntityAlias, EntityMention
from ai.entities.service import (
    add_mention,
    normalize_name,
    resolve_entity,
)


def _loads(value) -> list:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


async def _entity_count(db, user_id: int) -> int:
    return int((await db.execute(
        select(func.count()).select_from(Entity).where(Entity.user_id == user_id)
    )).scalar_one() or 0)


async def _add_alias(
    db,
    user_id: int,
    entity_id: int,
    alias: str | None,
    alias_type: str,
    source: str,
) -> None:
    value = (alias or "").strip()
    if not value:
        return
    existing = (await db.execute(
        select(EntityAlias.id).where(
            EntityAlias.user_id == user_id,
            EntityAlias.entity_id == entity_id,
            EntityAlias.alias == value[:300],
            EntityAlias.alias_type == alias_type,
        )
    )).scalar_one_or_none()
    if existing is None:
        db.add(EntityAlias(
            user_id=user_id,
            entity_id=entity_id,
            alias=value[:300],
            alias_type=alias_type,
            source=source,
            confidence=1.0,
        ))


async def seed_from_profile(db, user_id: int) -> dict:
    from core.auth.domain.models import UserProfile

    profile = await db.get(UserProfile, user_id)
    if profile is None:
        return {"entities": 0, "total": 0}

    before = await _entity_count(db, user_id)
    for contact in _loads(profile.contacts):
        if not isinstance(contact, dict):
            continue
        name = str(contact.get("name") or "").strip()
        if not name:
            continue
        entity = await resolve_entity(
            db, user_id, "person", name, source="profile"
        )
        if entity is None:
            continue
        await _add_alias(
            db, user_id, entity.id, contact.get("email"), "email", "profile"
        )
        await _add_alias(
            db, user_id, entity.id, contact.get("phone"), "phone", "profile"
        )
    for project in _loads(profile.projects):
        if not isinstance(project, dict):
            continue
        name = str(project.get("name") or "").strip()
        if name:
            await resolve_entity(
                db, user_id, "project", name, source="profile"
            )
    await db.flush()
    after = await _entity_count(db, user_id)
    return {"entities": after - before, "total": after}


async def attach_memory_entities(db, user_id: int, record) -> dict:
    """Attach a memory to person/project entities it mentions."""
    content = str(getattr(record, "content", "") or "")
    data = getattr(record, "data", None) or {}
    if not isinstance(data, dict):
        data = {}

    before = int((await db.execute(
        select(func.count()).select_from(EntityMention).where(
            EntityMention.user_id == user_id,
            EntityMention.source_type == "memory",
            EntityMention.source_id == record.id,
        )
    )).scalar_one() or 0)

    targets: list[tuple[str, str]] = []
    if data.get("person"):
        targets.append(("person", str(data["person"])))
    if data.get("project"):
        targets.append(("project", str(data["project"])))
    if data.get("topic"):
        targets.append(("topic", str(data["topic"])))

    entities = list((await db.execute(
        select(Entity).where(
            Entity.user_id == user_id,
            Entity.status == "active",
            Entity.type.in_(("person", "project", "topic")),
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
    known = {entity.id: entity for entity in entities}
    content_norm = normalize_name(content)

    matched: set[int] = set()
    for entity in entities:
        if normalize_name(entity.canonical_name) in content_norm:
            matched.add(entity.id)
    for alias in aliases:
        if alias.entity_id in known and normalize_name(alias.alias) in content_norm:
            matched.add(alias.entity_id)

    for entity_type, name in targets:
        entity = await resolve_entity(
            db, user_id, entity_type, name, source="memory"
        )
        if entity is not None:
            matched.add(entity.id)

    for entity_id in matched:
        entity = known.get(entity_id) or await db.get(Entity, entity_id)
        await add_mention(
            db,
            user_id,
            entity_id,
            source_type="memory",
            source_id=record.id,
            quote=content[:300],
            role="mentions",
            extracted_by="rule",
        )

    after = int((await db.execute(
        select(func.count()).select_from(EntityMention).where(
            EntityMention.user_id == user_id,
            EntityMention.source_type == "memory",
            EntityMention.source_id == record.id,
        )
    )).scalar_one() or 0)
    return {"mentions": after - before}
