"""Entity resolution and graph queries.

Resolution is deliberately conservative: exact aliases first, then exact
canonical names. Unknown names become new entities only when ``create`` is
true. Fuzzy merging belongs to a later phase.
"""

from __future__ import annotations

import re

from sqlalchemy import or_, select

from ai.entities.models import (
    Entity,
    EntityAlias,
    EntityMention,
    EntityRelation,
)

_NON_WORD = re.compile(r"[\s\W_]+", re.UNICODE)


def normalize_name(value: str | None) -> str:
    return _NON_WORD.sub("", (value or "").lower())


async def _load_entities(db, user_id: int, entity_type: str) -> list[Entity]:
    rows = await db.execute(
        select(Entity).where(
            Entity.user_id == user_id,
            Entity.type == entity_type,
            Entity.status == "active",
        )
    )
    return list(rows.scalars().all())


async def resolve_entity(
    db,
    user_id: int,
    entity_type: str,
    name: str,
    *,
    create: bool = True,
    alias_type: str = "name",
    source: str | None = None,
    confidence: float = 0.8,
) -> Entity | None:
    raw = (name or "").strip()
    if not raw:
        return None
    normalized = normalize_name(raw)
    if not normalized:
        return None

    entities = await _load_entities(db, user_id, entity_type)
    if not entities:
        if not create:
            return None
        return await _create_entity(
            db, user_id, entity_type, raw, alias_type, source, confidence
        )

    by_id = {entity.id: entity for entity in entities}
    aliases = list((await db.execute(
        select(EntityAlias).where(
            EntityAlias.user_id == user_id,
            EntityAlias.entity_id.in_(list(by_id)),
        )
    )).scalars().all())
    for alias in aliases:
        if normalize_name(alias.alias) == normalized:
            entity = by_id.get(alias.entity_id)
            if entity is not None:
                return entity

    for entity in entities:
        if normalize_name(entity.canonical_name) == normalized:
            await _ensure_alias(
                db, user_id, entity.id, entity.type, raw, alias_type,
                source, confidence,
            )
            return entity

    if not create:
        return None
    return await _create_entity(
        db, user_id, entity_type, raw, alias_type, source, confidence
    )


async def _ensure_alias(
    db,
    user_id: int,
    entity_id: int,
    entity_type: str,
    alias: str,
    alias_type: str,
    source: str | None,
    confidence: float,
) -> EntityAlias:
    existing = (await db.execute(
        select(EntityAlias).where(
            EntityAlias.user_id == user_id,
            EntityAlias.entity_id == entity_id,
            EntityAlias.alias == alias[:300],
            EntityAlias.alias_type == alias_type,
            EntityAlias.entity_type == entity_type,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return existing
    row = EntityAlias(
        user_id=user_id,
        entity_id=entity_id,
        alias=alias[:300],
        alias_type=alias_type,
        entity_type=entity_type,
        source=source,
        confidence=float(confidence),
    )
    db.add(row)
    await db.flush()
    return row


async def _create_entity(
    db,
    user_id: int,
    entity_type: str,
    name: str,
    alias_type: str,
    source: str | None,
    confidence: float,
) -> Entity:
    entity = Entity(
        user_id=user_id,
        type=entity_type,
        canonical_name=name[:200],
        status="active",
    )
    db.add(entity)
    await db.flush()
    await _ensure_alias(
        db, user_id, entity.id, entity_type, name, alias_type,
        source, confidence,
    )
    return entity


async def add_mention(
    db,
    user_id: int,
    entity_id: int,
    *,
    source_type: str,
    source_id: int,
    quote: str,
    role: str = "mentioned",
    confidence: float = 0.8,
    extracted_by: str = "rule",
) -> EntityMention:
    entity = await db.get(Entity, entity_id)
    if entity is None or entity.user_id != user_id:
        raise ValueError("entity does not belong to user")
    existing = (await db.execute(
        select(EntityMention).where(
            EntityMention.user_id == user_id,
            EntityMention.entity_id == entity_id,
            EntityMention.source_type == source_type,
            EntityMention.source_id == source_id,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return existing
    row = EntityMention(
        user_id=user_id,
        entity_id=entity_id,
        source_type=source_type,
        source_id=source_id,
        quote=(quote or "")[:2000] or None,
        role=role,
        confidence=float(confidence),
        extracted_by=extracted_by,
    )
    db.add(row)
    await db.flush()
    return row


async def add_relation(
    db,
    user_id: int,
    from_entity_id: int,
    to_entity_id: int,
    relation: str,
    *,
    confidence: float = 0.8,
    source_mention_id: int | None = None,
    valid_from=None,
    valid_to=None,
) -> EntityRelation:
    left = await db.get(Entity, from_entity_id)
    right = await db.get(Entity, to_entity_id)
    if (
        left is None
        or right is None
        or left.user_id != user_id
        or right.user_id != user_id
    ):
        raise ValueError("entity does not belong to user")
    existing = (await db.execute(
        select(EntityRelation).where(
            EntityRelation.user_id == user_id,
            EntityRelation.from_entity_id == from_entity_id,
            EntityRelation.to_entity_id == to_entity_id,
            EntityRelation.relation == relation,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return existing
    row = EntityRelation(
        user_id=user_id,
        from_entity_id=from_entity_id,
        to_entity_id=to_entity_id,
        relation=relation[:60],
        confidence=float(confidence),
        source_mention_id=source_mention_id,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    db.add(row)
    await db.flush()
    return row


async def related_entities(
    db,
    user_id: int,
    entity_ids: list[int],
    *,
    depth: int = 2,
    relations: list[str] | None = None,
) -> list[Entity]:
    seeds = {int(value) for value in entity_ids if value}
    if not seeds:
        return []
    seen = set(seeds)
    frontier = set(seeds)
    for _ in range(max(0, min(int(depth), 3))):
        q = select(EntityRelation).where(EntityRelation.user_id == user_id)
        if relations:
            q = q.where(EntityRelation.relation.in_(relations))
        q = q.where(or_(
            EntityRelation.from_entity_id.in_(frontier),
            EntityRelation.to_entity_id.in_(frontier),
        ))
        links = list((await db.execute(q)).scalars().all())
        nxt: set[int] = set()
        for link in links:
            if link.from_entity_id in frontier and link.to_entity_id not in seen:
                nxt.add(link.to_entity_id)
            if link.to_entity_id in frontier and link.from_entity_id not in seen:
                nxt.add(link.from_entity_id)
        if not nxt:
            break
        seen |= nxt
        frontier = nxt

    discovered = seen - seeds
    if not discovered:
        return []
    rows = list((await db.execute(
        select(Entity).where(
            Entity.user_id == user_id,
            Entity.id.in_(discovered),
            Entity.status == "active",
        )
    )).scalars().all())
    return rows


async def mentions_for_entities(
    db,
    user_id: int,
    entity_ids: list[int],
    *,
    source_types: list[str] | None = None,
    limit: int = 100,
) -> list[EntityMention]:
    ids = [int(value) for value in entity_ids if value]
    if not ids:
        return []
    q = select(EntityMention).where(
        EntityMention.user_id == user_id,
        EntityMention.entity_id.in_(ids),
    )
    if source_types:
        q = q.where(EntityMention.source_type.in_(source_types))
    q = q.order_by(EntityMention.id.desc()).limit(max(1, min(int(limit), 500)))
    return list((await db.execute(q)).scalars().all())


