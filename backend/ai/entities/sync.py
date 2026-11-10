"""Sync legacy vector entities into the canonical entity graph."""

from __future__ import annotations

import json
from collections import defaultdict

from sqlalchemy import and_, delete, or_, select, text

from ai.entities.models import Entity, EntityMention, EntityRelation
from ai.entities.service import (
    add_mention,
    add_relation,
    normalize_name,
    resolve_entity,
)
from core.database.session import async_session, engine
from core.logging import get_logger

log = get_logger(__name__)

_EXTERNAL_SOURCES = {"sources", "source_item", "rss", "rss_entry", "article"}
_TYPE_ALIASES = {
    "person": "person",
    "project": "project",
    "term": "term",
    "product": "product",
    "organization": "organization",
    "org": "organization",
    "location": "location",
    "place": "location",
    "event": "event",
    "topic": "topic",
    "technology": "technology",
    "task": "task",
    "document": "document",
}


def _loads(value):
    if isinstance(value, (list, dict)):
        return value
    if not value:
        return []
    try:
        return json.loads(value)
    except Exception:
        return []


def _canonical_type(value: str | None) -> str:
    return _TYPE_ALIASES.get(str(value or "term").lower(), "term")


def _is_external(meta: dict) -> bool:
    sources = [item for item in (meta.get("sources") or []) if isinstance(item, dict)]
    if not sources:
        return False
    return all((item.get("type") or "") in _EXTERNAL_SOURCES for item in sources)


def _relation_for(
    left: Entity, right: Entity, source_type: str
) -> tuple[int, int, str] | None:
    """Return (from_id, to_id, relation) for a pair of entities."""
    lt, rt = left.type, right.type
    if lt == "person" and rt == "person":
        relation = (
            "communicates_with"
            if source_type in ("mail", "dingtalk", "chat", "meeting")
            else "knows"
        )
        return left.id, right.id, relation
    if lt == "person" and rt in ("project", "task", "goal"):
        return left.id, right.id, "works_on"
    if rt == "person" and lt in ("project", "task", "goal"):
        return right.id, left.id, "works_on"
    if lt == "person" and rt in ("task", "todo"):
        return left.id, right.id, "assigned_to"
    if rt == "person" and lt in ("task", "todo"):
        return right.id, left.id, "assigned_to"
    if lt == "person" and rt == "organization":
        return left.id, right.id, "member_of"
    if rt == "person" and lt == "organization":
        return right.id, left.id, "member_of"
    if lt in ("project", "goal", "task") and rt in ("product", "technology"):
        return left.id, right.id, "uses"
    if rt in ("project", "goal", "task") and lt in ("product", "technology"):
        return right.id, left.id, "uses"
    if lt in ("project", "goal", "task") and rt in ("topic", "term", "document"):
        return left.id, right.id, "about"
    if rt in ("project", "goal", "task") and lt in ("topic", "term", "document"):
        return right.id, left.id, "about"
    if lt == "organization" and rt in ("project", "goal"):
        return left.id, right.id, "owns"
    if rt == "organization" and lt in ("project", "goal"):
        return right.id, left.id, "owns"
    a, b = sorted((left.id, right.id))
    return a, b, "related_to"


async def sync_embedding_entities(user_id: int | None = None) -> dict:
    """Create canonical entities/aliases/mentions from vector entities."""
    if engine.dialect.name != "postgresql":
        return {"entities": 0, "mentions": 0, "skipped": True}
    query = (
        "SELECT user_id, doc_key, title, metadata FROM embeddings "
        "WHERE collection = 'entities'"
    )
    params: dict = {}
    if user_id is not None:
        query += " AND user_id = :uid"
        params["uid"] = user_id
    async with engine.begin() as conn:
        rows = (await conn.execute(text(query), params)).mappings().all()

    created = 0
    mentions = 0
    async with async_session() as db:
        for row in rows:
            meta = _loads(row["metadata"]) or {}
            if meta.get("type") == "memory" or _is_external(meta):
                continue
            name = str(row["title"] or meta.get("name") or "").strip()
            if not name:
                continue
            entity_type = _canonical_type(meta.get("type"))
            entity = await resolve_entity(
                db,
                int(row["user_id"]),
                entity_type,
                name,
                source="embeddings",
                confidence=float(meta.get("confidence") or 0.7),
            )
            if entity is None:
                continue
            created += 1
            for source in meta.get("sources") or []:
                if not isinstance(source, dict) or source.get("id") is None:
                    continue
                source_type = str(source.get("type") or "unknown")
                source_id = int(source["id"])
                quote = str(source.get("title") or name)[:300]
                await add_mention(
                    db,
                    int(row["user_id"]),
                    entity.id,
                    source_type=source_type,
                    source_id=source_id,
                    quote=quote,
                    role="mentions",
                    confidence=0.7,
                    extracted_by="import",
                )
                mentions += 1
        await db.commit()
    return {"entities": created, "mentions": mentions, "skipped": False}


async def derive_relations(user_id: int | None = None) -> dict:
    """Derive typed relations from entities that co-occur in one source."""
    async with async_session() as db:
        entity_q = select(Entity).where(Entity.status == "active")
        if user_id is not None:
            entity_q = entity_q.where(Entity.user_id == user_id)
        entities = list((await db.execute(entity_q)).scalars().all())
        if not entities:
            return {"relations": 0}
        by_id = {entity.id: entity for entity in entities}
        mention_q = select(EntityMention).where(
            EntityMention.entity_id.in_(list(by_id))
        )
        mentions = list((await db.execute(mention_q)).scalars().all())

        groups: dict[tuple[str, int], set[int]] = defaultdict(set)
        for mention in mentions:
            groups[(mention.source_type, mention.source_id)].add(mention.entity_id)

        created = 0
        for (source_type, source_id), ids in groups.items():
            if len(ids) < 2 or len(ids) > 12:
                continue
            ordered = sorted(ids)
            for i in range(len(ordered)):
                for j in range(i + 1, len(ordered)):
                    left = by_id.get(ordered[i])
                    right = by_id.get(ordered[j])
                    if left is None or right is None:
                        continue
                    mapped = _relation_for(left, right, source_type)
                    if mapped is None:
                        continue
                    from_id, to_id, relation = mapped
                    await add_relation(
                        db,
                        left.user_id,
                        from_id,
                        to_id,
                        relation,
                        confidence=0.65 if relation != "related_to" else 0.45,
                        meta={
                            "source": "cooccurrence",
                            "source_type": source_type,
                            "source_id": source_id,
                        },
                    )
                    if relation != "related_to":
                        await db.execute(
                            delete(EntityRelation).where(
                                EntityRelation.user_id == left.user_id,
                                or_(
                                    and_(
                                        EntityRelation.from_entity_id == from_id,
                                        EntityRelation.to_entity_id == to_id,
                                    ),
                                    and_(
                                        EntityRelation.from_entity_id == to_id,
                                        EntityRelation.to_entity_id == from_id,
                                    ),
                                ),
                                EntityRelation.relation == "related_to",
                            )
                        )
                    created += 1
        await db.commit()
    return {"relations": created}


async def sync_all(user_id: int | None = None) -> dict:
    synced = await sync_embedding_entities(user_id)
    derived = await derive_relations(user_id)
    return {**synced, **derived}
