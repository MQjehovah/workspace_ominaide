"""Entity resolution and graph queries.

Resolution is deliberately conservative: exact aliases first, then exact
canonical names. Unknown names become new entities only when ``create`` is
true. Fuzzy merging belongs to a later phase.
"""

from __future__ import annotations

import re

from sqlalchemy import delete, or_, select

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
            if alias_type == "name":
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
    meta: dict | None = None,
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
        if confidence > (existing.confidence or 0):
            existing.confidence = float(confidence)
        if meta:
            existing.meta = {**(existing.meta or {}), **meta}
        await db.flush()
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
        meta=meta,
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




async def graph_context(
    db,
    user_id: int,
    text: str,
    *,
    limit: int = 8,
    depth: int = 2,
) -> dict:
    """Resolve entities mentioned in text and expand their graph neighborhood."""
    normalized = normalize_name(text)
    if not normalized:
        return {"entities": [], "relations": [], "mentions": []}

    entities = list((await db.execute(
        select(Entity).where(
            Entity.user_id == user_id,
            Entity.status == "active",
        )
    )).scalars().all())
    if not entities:
        return {"entities": [], "relations": [], "mentions": []}
    by_id = {entity.id: entity for entity in entities}
    aliases = list((await db.execute(
        select(EntityAlias).where(
            EntityAlias.user_id == user_id,
            EntityAlias.entity_id.in_(list(by_id)),
        )
    )).scalars().all())
    alias_map: dict[int, list[str]] = {}
    for alias in aliases:
        alias_map.setdefault(alias.entity_id, []).append(alias.alias)

    seeds: list[Entity] = []
    for entity in entities:
        names = [entity.canonical_name, *alias_map.get(entity.id, [])]
        if any(
            normalize_name(name) and normalize_name(name) in normalized
            for name in names
        ):
            seeds.append(entity)
        if len(seeds) >= limit:
            break
    if not seeds:
        return {"entities": [], "relations": [], "mentions": []}

    seed_ids = [entity.id for entity in seeds]
    related = await related_entities(
        db, user_id, seed_ids, depth=depth
    )
    all_entities = {entity.id: entity for entity in [*seeds, *related]}

    relation_rows = list((await db.execute(
        select(EntityRelation).where(
            EntityRelation.user_id == user_id,
            or_(
                EntityRelation.from_entity_id.in_(list(all_entities)),
                EntityRelation.to_entity_id.in_(list(all_entities)),
            ),
        ).limit(max(20, limit * 6))
    )).scalars().all())
    relations = []
    for relation in relation_rows:
        left = all_entities.get(relation.from_entity_id)
        right = all_entities.get(relation.to_entity_id)
        if left is None or right is None:
            continue
        relations.append({
            "from_id": left.id,
            "from_name": left.canonical_name,
            "relation": relation.relation,
            "to_id": right.id,
            "to_name": right.canonical_name,
            "confidence": relation.confidence,
        })

    mention_rows = await mentions_for_entities(
        db, user_id, list(all_entities), limit=max(20, limit * 4)
    )
    mentions = [
        {
            "entity_id": mention.entity_id,
            "entity_name": all_entities[mention.entity_id].canonical_name
            if mention.entity_id in all_entities else "",
            "source_type": mention.source_type,
            "source_id": mention.source_id,
            "quote": (mention.quote or "")[:240],
            "role": mention.role,
        }
        for mention in mention_rows
    ]
    return {
        "entities": [
            {
                "id": entity.id,
                "name": entity.canonical_name,
                "type": entity.type,
                "aliases": alias_map.get(entity.id, []),
            }
            for entity in [*seeds, *related]
        ],
        "relations": relations,
        "mentions": mentions,
    }


async def merge_entities(
    db,
    user_id: int,
    source_id: int,
    target_id: int,
) -> Entity:
    """Merge one canonical entity into another, keeping aliases/mentions."""
    if source_id == target_id:
        raise ValueError("cannot merge an entity into itself")
    source = await db.get(Entity, source_id)
    target = await db.get(Entity, target_id)
    if source is None or target is None:
        raise ValueError("entity not found")
    if source.user_id != user_id or target.user_id != user_id:
        raise ValueError("entity does not belong to user")
    if source.status != "active" or target.status != "active":
        raise ValueError("entity is not active")

    aliases = list((await db.execute(
        select(EntityAlias).where(
            EntityAlias.user_id == user_id,
            EntityAlias.entity_id == source.id,
        )
    )).scalars().all())
    for alias in aliases:
        existing = (await db.execute(
            select(EntityAlias).where(
                EntityAlias.user_id == user_id,
                EntityAlias.entity_id == target.id,
                EntityAlias.alias == alias.alias,
                EntityAlias.alias_type == alias.alias_type,
                EntityAlias.entity_type == alias.entity_type,
            )
        )).scalar_one_or_none()
        if existing is not None:
            await db.delete(alias)
        else:
            alias.entity_id = target.id

    await _ensure_alias(
        db, user_id, target.id, target.type, source.canonical_name,
        "name", "merge", 1.0,
    )

    mentions = list((await db.execute(
        select(EntityMention).where(
            EntityMention.user_id == user_id,
            EntityMention.entity_id == source.id,
        )
    )).scalars().all())
    for mention in mentions:
        existing = (await db.execute(
            select(EntityMention).where(
                EntityMention.user_id == user_id,
                EntityMention.entity_id == target.id,
                EntityMention.source_type == mention.source_type,
                EntityMention.source_id == mention.source_id,
            )
        )).scalar_one_or_none()
        if existing is not None:
            await db.delete(mention)
        else:
            mention.entity_id = target.id

    relations = list((await db.execute(
        select(EntityRelation).where(
            EntityRelation.user_id == user_id,
            or_(
                EntityRelation.from_entity_id == source.id,
                EntityRelation.to_entity_id == source.id,
            ),
        )
    )).scalars().all())
    for relation in relations:
        new_from = target.id if relation.from_entity_id == source.id else relation.from_entity_id
        new_to = target.id if relation.to_entity_id == source.id else relation.to_entity_id
        if new_from == new_to:
            await db.delete(relation)
            continue
        existing = (await db.execute(
            select(EntityRelation).where(
                EntityRelation.user_id == user_id,
                EntityRelation.from_entity_id == new_from,
                EntityRelation.to_entity_id == new_to,
                EntityRelation.relation == relation.relation,
            )
        )).scalar_one_or_none()
        if existing is not None:
            await db.delete(relation)
        else:
            relation.from_entity_id = new_from
            relation.to_entity_id = new_to

    source.status = "merged"
    source.merged_into = target.id
    await db.flush()
    return target


async def merge_suggestions(db, user_id: int, limit: int = 20) -> list[dict]:
    """Suggest likely duplicate entities for manual merge."""
    from difflib import SequenceMatcher

    entities = list((await db.execute(
        select(Entity).where(
            Entity.user_id == user_id,
            Entity.status == "active",
        )
    )).scalars().all())
    aliases = list((await db.execute(
        select(EntityAlias).where(
            EntityAlias.user_id == user_id,
            EntityAlias.entity_id.in_([entity.id for entity in entities]) if entities else [],
        )
    )).scalars().all())
    alias_map: dict[int, list[str]] = {}
    for alias in aliases:
        alias_map.setdefault(alias.entity_id, []).append(alias.alias)

    names: list[tuple[Entity, str]] = []
    for entity in entities:
        values = [entity.canonical_name, *alias_map.get(entity.id, [])]
        for value in values:
            normalized = normalize_name(value)
            if normalized:
                names.append((entity, normalized))

    suggestions: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for i in range(len(names)):
        left, left_name = names[i]
        for j in range(i + 1, len(names)):
            right, right_name = names[j]
            if left.id == right.id or left.type != right.type:
                continue
            key = (min(left.id, right.id), max(left.id, right.id))
            if key in seen:
                continue
            if left_name == right_name:
                score, reason = 1.0, "名称完全相同"
            elif (
                min(len(left_name), len(right_name)) >= 3
                and (left_name in right_name or right_name in left_name)
            ):
                score = 0.9
                reason = "名称包含关系"
            else:
                score = SequenceMatcher(None, left_name, right_name).ratio()
                reason = "名称相似"
            if score < 0.82:
                continue
            seen.add(key)
            suggestions.append({
                "a": {"id": left.id, "name": left.canonical_name, "type": left.type},
                "b": {"id": right.id, "name": right.canonical_name, "type": right.type},
                "score": round(score, 3),
                "reason": reason,
            })
    suggestions.sort(key=lambda item: item["score"], reverse=True)
    return suggestions[: max(1, min(limit, 100))]
