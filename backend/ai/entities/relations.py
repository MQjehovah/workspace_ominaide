"""LLM-assisted typed relation extraction for the entity graph."""

from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict

from sqlalchemy import and_, delete, or_, select

from ai.entities.models import Entity, EntityAlias, EntityMention, EntityRelation
from ai.entities.service import add_relation, normalize_name
from ai.entities.sources import load_source_text
from ai.llm.usage import tracked_create
from core.config.settings import settings
from core.database.session import async_session
from core.logging import get_logger

log = get_logger(__name__)

RELATION_TYPES = {
    "works_on", "assigned_to", "member_of", "owns", "uses", "about",
    "communicates_with", "knows", "located_in", "part_of", "related_to",
}

_SYSTEM_PROMPT = """你是个人知识图谱的实体关系抽取器。
只根据原文中明确出现的事实抽取关系，不要根据常识猜测。
关系类型只能是：
works_on(负责/参与), assigned_to(被分配), member_of(属于组织),
owns(拥有/负责), uses(使用), about(关于), communicates_with(沟通),
knows(认识), located_in(位于), part_of(属于), related_to(相关)。

只返回 JSON，不要输出其他文字：
{"relations":[{"from":"实体A","relation":"works_on","to":"实体B","confidence":0.0,"evidence":"原文短句"}]}
没有明确关系时返回 {"relations":[]}。from/to 必须使用给定实体名称。"""


def _clip(value, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def _match_entities(
    entities: list[Entity],
    alias_map: dict[int, list[str]],
    text: str,
    *,
    limit: int = 12,
) -> list[Entity]:
    normalized = normalize_name(text)
    if not normalized:
        return []
    matched: list[Entity] = []
    for entity in entities:
        names = [entity.canonical_name, *alias_map.get(entity.id, [])]
        if any(
            normalize_name(name) and normalize_name(name) in normalized
            for name in names
        ):
            matched.append(entity)
    return matched[:limit]


def _resolve_name(names: dict[str, Entity], value: str) -> Entity | None:
    normalized = normalize_name(value)
    if not normalized:
        return None
    for name, entity in names.items():
        if normalize_name(name) == normalized:
            return entity
    for name, entity in names.items():
        candidate = normalize_name(name)
        if candidate and (candidate in normalized or normalized in candidate):
            return entity
    return None


async def _recent_texts(db, user_id: int, limit: int = 12) -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    try:
        from plugins.notes.backend.models import PluginNote

        notes = list((await db.execute(
            select(PluginNote)
            .where(PluginNote.user_id == user_id, PluginNote.is_folder == 0)
            .order_by(PluginNote.updated_at.desc())
            .limit(4)
        )).scalars().all())
        for row in notes:
            out.append(("note", row.id, f"{row.title or ''}\n{row.content or ''}"))
    except Exception:
        pass
    try:
        from ai.memory.models import MemoryRecord

        memories = list((await db.execute(
            select(MemoryRecord)
            .where(
                MemoryRecord.user_id == user_id,
                MemoryRecord.status == "active",
            )
            .order_by(MemoryRecord.updated_at.desc())
            .limit(6)
        )).scalars().all())
        for row in memories:
            out.append(("memory", row.id, str(row.content or "")))
    except Exception:
        pass
    try:
        from plugins.mail.backend.models import MailMessage

        mails = list((await db.execute(
            select(MailMessage)
            .where(MailMessage.user_id == user_id)
            .order_by(MailMessage.date.desc())
            .limit(3)
        )).scalars().all())
        for row in mails:
            out.append((
                "mail",
                row.id,
                f"{row.subject or ''}\n{row.from_address or ''}\n"
                f"{row.content or row.preview or ''}",
            ))
    except Exception:
        pass
    return [item for item in out if len(item[2].strip()) >= 40][:limit]


async def _extract_for_source(
    db,
    user_id: int,
    source_type: str,
    source_id: int,
    group_entities: list[Entity],
    alias_map: dict[int, list[str]],
    text: str,
) -> int:
    if len(group_entities) < 2 or len(text.strip()) < 40:
        return 0
    names: dict[str, Entity] = {}
    for entity in group_entities:
        names[entity.canonical_name] = entity
        for alias in alias_map.get(entity.id, []):
            names[alias] = entity
    entity_lines = "\n".join(
        f"- {entity.canonical_name} ({entity.type})" for entity in group_entities
    )
    prompt = (
        f"实体列表：\n{entity_lines}\n\n"
        f"来源类型：{source_type}\n原文：\n{text[:3000]}"
    )
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
        response = await tracked_create(
            client,
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        raw = response.choices[0].message.content or "{}"
        match = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(match.group(0)) if match else {}
        rows = data.get("relations") if isinstance(data, dict) else []
    except Exception as exc:
        log.warning("[entities] relation extraction failed: %s", exc)
        return 0

    created = 0
    for row in rows[:20]:
        if not isinstance(row, dict):
            continue
        relation = str(row.get("relation") or "related_to").strip()
        if relation not in RELATION_TYPES:
            relation = "related_to"
        left = _resolve_name(names, str(row.get("from") or ""))
        right = _resolve_name(names, str(row.get("to") or ""))
        if left is None or right is None or left.id == right.id:
            continue
        try:
            confidence = float(row.get("confidence") or 0.7)
        except (TypeError, ValueError):
            confidence = 0.7
        confidence = max(0.1, min(confidence, 0.99))
        await add_relation(
            db,
            user_id,
            left.id,
            right.id,
            relation,
            confidence=confidence,
            meta={
                "source": "llm",
                "source_type": source_type,
                "source_id": source_id,
                "evidence": _clip(row.get("evidence")),
            },
        )
        if relation != "related_to":
            await db.execute(
                delete(EntityRelation).where(
                    EntityRelation.user_id == user_id,
                    or_(
                        and_(
                            EntityRelation.from_entity_id == left.id,
                            EntityRelation.to_entity_id == right.id,
                        ),
                        and_(
                            EntityRelation.from_entity_id == right.id,
                            EntityRelation.to_entity_id == left.id,
                        ),
                    ),
                    EntityRelation.relation == "related_to",
                )
            )
        created += 1
    return created


async def extract_relations_for_user(
    user_id: int,
    *,
    limit_sources: int = 8,
) -> dict:
    if not settings.llm_api_key:
        return {"sources": 0, "relations": 0, "skipped": True}

    async with async_session() as db:
        entities = list((await db.execute(
            select(Entity).where(
                Entity.user_id == user_id,
                Entity.status == "active",
            )
        )).scalars().all())
        if len(entities) < 2:
            return {"sources": 0, "relations": 0, "skipped": True}
        by_id = {entity.id: entity for entity in entities}
        aliases = list((await db.execute(
            select(EntityAlias).where(
                EntityAlias.user_id == user_id,
                EntityAlias.entity_id.in_(list(by_id)),
            )
        )).scalars().all())
        mentions = list((await db.execute(
            select(EntityMention).where(
                EntityMention.user_id == user_id,
                EntityMention.entity_id.in_(list(by_id)),
            ).order_by(EntityMention.id.desc()).limit(1200)
        )).scalars().all())

        alias_map: dict[int, list[str]] = defaultdict(list)
        for alias in aliases:
            alias_map[alias.entity_id].append(alias.alias)

        groups: dict[tuple[str, int], list[EntityMention]] = defaultdict(list)
        for mention in mentions:
            groups[(mention.source_type, mention.source_id)].append(mention)

        recent_tasks: list[tuple[str, int, list[Entity], str]] = []
        mention_tasks: list[tuple[str, int, list[Entity], str]] = []
        processed: set[tuple[str, int]] = set()
        for (source_type, source_id), items in groups.items():
            entity_ids = sorted({item.entity_id for item in items})
            group_entities = [
                by_id[entity_id] for entity_id in entity_ids if entity_id in by_id
            ]
            if not (2 <= len(group_entities) <= 12):
                continue
            text = await load_source_text(
                db, user_id, source_type, source_id, limit=3500
            )
            if len(text.strip()) < 40:
                continue
            processed.add((source_type, source_id))
            mention_tasks.append((source_type, source_id, group_entities, text))

        for source_type, source_id, text in await _recent_texts(db, user_id):
            key = (source_type, source_id)
            if key in processed:
                continue
            group_entities = _match_entities(entities, alias_map, text)
            if len(group_entities) < 2:
                continue
            processed.add(key)
            recent_tasks.append((source_type, source_id, group_entities, text))

    tasks = recent_tasks + mention_tasks

    created = 0
    used_sources = 0
    for source_type, source_id, group_entities, text in tasks[: max(1, min(limit_sources, 20))]:
        async with async_session() as db:
            created += await _extract_for_source(
                db,
                user_id,
                source_type,
                source_id,
                group_entities,
                alias_map,
                text,
            )
            await db.commit()
        used_sources += 1

    return {"sources": used_sources, "relations": created, "skipped": False}


_user_locks: dict[int, asyncio.Lock] = {}


async def extract_relations_from_text(
    user_id: int,
    text: str,
    source_type: str,
    source_id: int,
) -> dict:
    """Extract relations for one freshly indexed source, skipping if busy."""
    if len((text or "").strip()) < 40 or not settings.llm_api_key:
        return {"relations": 0, "skipped": True}
    lock = _user_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _user_locks[user_id] = lock
    if lock.locked():
        return {"relations": 0, "skipped": True}
    async with lock:
        async with async_session() as db:
            entities = list((await db.execute(
                select(Entity).where(
                    Entity.user_id == user_id,
                    Entity.status == "active",
                )
            )).scalars().all())
            if len(entities) < 2:
                return {"relations": 0, "skipped": True}
            aliases = list((await db.execute(
                select(EntityAlias).where(
                    EntityAlias.user_id == user_id,
                    EntityAlias.entity_id.in_([entity.id for entity in entities]),
                )
            )).scalars().all())
            alias_map: dict[int, list[str]] = defaultdict(list)
            for alias in aliases:
                alias_map[alias.entity_id].append(alias.alias)
            matched = _match_entities(entities, alias_map, text)
            if len(matched) < 2:
                return {"relations": 0, "skipped": False}
            created = await _extract_for_source(
                db, user_id, source_type, source_id, matched, alias_map, text
            )
            await db.commit()
            return {"relations": created, "skipped": False}
