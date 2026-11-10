"""User memory: profile, AI-learned preferences and the entity graph."""

from __future__ import annotations

from core.logging import get_logger
log = get_logger(__name__)

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from core.auth.dependencies import get_current_user
from core.database.session import async_session, engine


router = APIRouter(prefix="/api/memory", tags=["memory"])


def _loads(value):
    if not value:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return None


_EXTERNAL_ENTITY_SOURCES = {"sources", "source_item", "rss", "rss_entry", "article"}


def _is_external_entity(meta: dict) -> bool:
    """True when every source of an entity is an external article feed.

    资讯 articles are reading material, not the user's own business objects, so
    historical entities extracted from them must not appear in the graph.
    """
    sources = [
        source for source in (meta.get("sources") or [])
        if isinstance(source, dict)
    ]
    if not sources:
        return False
    return all(
        (source.get("type") or "") in _EXTERNAL_ENTITY_SOURCES
        for source in sources
    )


@router.get("/profile")
async def memory_profile(user: dict = Depends(get_current_user)):
    from sqlalchemy import select
    from core.auth.domain.models import UserProfile

    async with async_session() as db:
        profile = (await db.execute(
            select(UserProfile).where(UserProfile.user_id == user["id"])
        )).scalar_one_or_none()
    if profile is None:
        return {
            "user_id": user["id"], "name": None, "role": None, "company": None,
            "contacts": [], "projects": [], "preferences": {},
        }
    prefs = _loads(profile.preferences) or {}
    return {
        "user_id": profile.user_id,
        "name": profile.name,
        "role": profile.role,
        "company": profile.company,
        "contacts": _loads(profile.contacts) or [],
        "projects": _loads(profile.projects) or [],
        "preferences": prefs,
        "interests": prefs.get("interests") or [],
        "habits": prefs.get("habits") or [],
        "insights": prefs.get("insights") or {},
        "last_analysis": prefs.get("last_analysis"),
    }


@router.get("/entities")
async def list_entities(
    entity_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    """List extracted people/projects/terms. Returns [] outside PostgreSQL."""
    if engine.dialect.name != "postgresql":
        return {"items": [], "counts": {}, "supported": False}
    try:
        async with engine.begin() as conn:
            rows = (await conn.execute(
                text(
                    "SELECT doc_key, title, metadata, created_at FROM embeddings "
                    "WHERE collection = 'entities' AND user_id = :uid "
                    "ORDER BY created_at DESC LIMIT :limit"
                ),
                {"uid": user["id"], "limit": limit},
            )).mappings().all()
    except Exception as e:
        log.warning(f"[memory] entities error: {e}")
        return {"items": [], "counts": {}, "supported": False}

    items = []
    counts: dict[str, int] = {}
    for row in rows:
        meta = row["metadata"]
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        meta = meta or {}
        if _is_external_entity(meta):
            continue
        etype = meta.get("type") or "term"
        if entity_type and etype != entity_type:
            continue
        counts[etype] = counts.get(etype, 0) + 1
        items.append({
            "id": row["doc_key"],
            "name": row["title"],
            "type": etype,
            "sources": meta.get("sources") or [],
            "first_seen": meta.get("first_seen"),
            "last_seen": meta.get("last_seen"),
        })
    return {"items": items, "counts": counts, "supported": True}


_NOISE_ENTITY_NAMES = {
    "项目", "任务", "需求", "问题", "功能", "模块", "系统", "平台", "服务",
    "接口", "数据", "配置", "代码", "文档", "测试", "版本", "上线",
    "backend", "frontend", "feature", "main", "git", "公司", "部门",
    "客户", "经办人", "负责人", "工单",
}


@router.get("/entities/graph")
async def entity_graph(
    entity_type: str | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    q: str = Query(""),
    include_noise: bool = Query(False),
    user: dict = Depends(get_current_user),
):
    """Canonical entity graph: aliases, mentions and typed relations."""
    from ai.entities.models import (
        Entity,
        EntityAlias,
        EntityMention,
        EntityRelation,
    )
    from sqlalchemy import or_, select

    query_text = (q or "").strip().lower()
    async with async_session() as db:
        entity_q = select(Entity).where(
            Entity.user_id == user["id"],
            Entity.status == "active",
        )
        if entity_type:
            entity_q = entity_q.where(Entity.type == entity_type)
        entities = list((await db.execute(
            entity_q.order_by(Entity.updated_at.desc()).limit(limit)
        )).scalars().all())
        if not entities:
            return {"nodes": [], "links": [], "counts": {}, "supported": True}

        if not query_text and not include_noise:
            entities = [
                entity for entity in entities
                if entity.canonical_name.strip().lower() not in _NOISE_ENTITY_NAMES
            ]
        if not entities:
            return {"nodes": [], "links": [], "counts": {}, "supported": True}
        ids = [entity.id for entity in entities]
        aliases = list((await db.execute(
            select(EntityAlias).where(
                EntityAlias.user_id == user["id"],
                EntityAlias.entity_id.in_(ids),
            )
        )).scalars().all())
        mentions = list((await db.execute(
            select(EntityMention).where(
                EntityMention.user_id == user["id"],
                EntityMention.entity_id.in_(ids),
            )
        )).scalars().all())
        relations = list((await db.execute(
            select(EntityRelation).where(
                EntityRelation.user_id == user["id"],
                or_(
                    EntityRelation.from_entity_id.in_(ids),
                    EntityRelation.to_entity_id.in_(ids),
                ),
            )
        )).scalars().all())

    alias_map: dict[int, list[str]] = {}
    for alias in aliases:
        alias_map.setdefault(alias.entity_id, []).append(alias.alias)

    mention_map: dict[int, list[EntityMention]] = {}
    for mention in mentions:
        mention_map.setdefault(mention.entity_id, []).append(mention)

    nodes = []
    counts: dict[str, int] = {}
    by_id = {}
    for entity in entities:
        names = [entity.canonical_name, *alias_map.get(entity.id, [])]
        if query_text and not any(query_text in str(name).lower() for name in names):
            continue
        own_mentions = mention_map.get(entity.id, [])
        sources = []
        seen_sources = set()
        for mention in own_mentions:
            key = (mention.source_type, mention.source_id)
            if key in seen_sources:
                continue
            seen_sources.add(key)
            sources.append({
                "type": mention.source_type,
                "id": mention.source_id,
                "title": (mention.quote or f"{mention.source_type} #{mention.source_id}")[:120],
            })
        stamps = [m.created_at for m in own_mentions if m.created_at]
        node = {
            "id": str(entity.id),
            "name": entity.canonical_name,
            "type": entity.type,
            "aliases": alias_map.get(entity.id, []),
            "source_count": len(sources),
            "sources": sources[:8],
            "first_seen": min(stamps).isoformat() if stamps else None,
            "last_seen": max(stamps).isoformat() if stamps else None,
            "degree": 0,
        }
        nodes.append(node)
        by_id[entity.id] = node
        counts[entity.type] = counts.get(entity.type, 0) + 1

    if not nodes:
        return {"nodes": [], "links": [], "counts": {}, "supported": True}

    allowed = {int(node_id) for node_id in by_id}
    seen_pairs: set[tuple[int, int]] = set()
    links = []
    for relation in relations:
        a, b = relation.from_entity_id, relation.to_entity_id
        if a not in allowed or b not in allowed or a == b:
            continue
        left, right = sorted((a, b))
        seen_pairs.add((left, right))
        links.append({
            "source": str(a),
            "target": str(b),
            "relation": relation.relation,
            "weight": max(1, int(round((relation.confidence or 0.5) * 3))),
            "confidence": relation.confidence,
        })

    # Fill gaps with co-occurrence links when a source mentions several
    # entities but no typed relation was extracted.
    groups: dict[tuple[str, int], set[int]] = {}
    for mention in mentions:
        if mention.entity_id not in allowed:
            continue
        groups.setdefault(
            (mention.source_type, mention.source_id), set()
        ).add(mention.entity_id)
    for ids_in_source in groups.values():
        if len(ids_in_source) < 2 or len(ids_in_source) > 12:
            continue
        ordered = sorted(ids_in_source)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                a, b = ordered[i], ordered[j]
                if (a, b) in seen_pairs:
                    continue
                seen_pairs.add((a, b))
                links.append({
                    "source": str(a),
                    "target": str(b),
                    "relation": "同一来源",
                    "weight": 1,
                    "confidence": 0.4,
                })

    for link in links:
        by_id[int(link["source"])]["degree"] += 1
        by_id[int(link["target"])]["degree"] += 1

    return {"nodes": nodes, "links": links, "counts": counts, "supported": True}


class CandidateApprove(BaseModel):
    pass


class RecordUpdate(BaseModel):
    content: str | None = None
    importance: int | None = None
    state: str | None = None


@router.get("/candidates")
async def candidates(
    status: str = Query("pending"),
    limit: int = Query(100, ge=1, le=300),
    user: dict = Depends(get_current_user),
):
    from ai.memory.service import list_candidates

    rows = await list_candidates(user["id"], status, limit)
    return {"items": [_candidate_out(r) for r in rows]}


@router.post("/candidates/{candidate_id}/approve")
async def approve_candidate(candidate_id: int, user: dict = Depends(get_current_user)):
    from ai.memory.service import approve_candidate as approve

    record = await approve(user["id"], candidate_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Candidate not found or already reviewed")
    await _record_candidate_review(user["id"], candidate_id, True, record.id)
    return {"message": "Approved", "record_id": record.id}


@router.post("/candidates/{candidate_id}/reject")
async def reject_candidate(candidate_id: int, user: dict = Depends(get_current_user)):
    from ai.memory.service import reject_candidate as reject

    ok = await reject(user["id"], candidate_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Candidate not found or already reviewed")
    await _record_candidate_review(user["id"], candidate_id, False)
    return {"message": "Rejected"}


async def _record_candidate_review(
    user_id: int, candidate_id: int, approved: bool, record_id: int | None = None,
) -> None:
    """Keep a rich audit trail of what the user accepted or ignored."""
    try:
        from sqlalchemy import select
        from core.database.session import async_session
        from core.events.bus import record_event
        from ai.memory.models import MemoryCandidate

        async with async_session() as db:
            cand = (await db.execute(
                select(MemoryCandidate).where(
                    MemoryCandidate.id == candidate_id,
                    MemoryCandidate.user_id == user_id,
                )
            )).scalar_one_or_none()
            if cand is None:
                return
            verb = "通过" if approved else "忽略"
            await record_event(
                db, user_id,
                "memory.candidate.approved" if approved else "memory.candidate.rejected",
                "memory", candidate_id,
                f"{verb}记忆: {(cand.content or '')[:80]}",
                {
                    "candidate_id": candidate_id,
                    "record_id": record_id,
                    "kind": cand.kind,
                    "confidence": cand.confidence,
                    "source_type": cand.source_type,
                    "source_id": cand.source_id,
                    "bot_id": cand.bot_id,
                    "trust": cand.trust,
                    "content": (cand.content or "")[:1000],
                },
            )
            await db.commit()
    except Exception as e:
        log.warning(f"[memory] candidate activity record failed: {e}")


@router.get("/records")
async def records(
    q: str = Query(""),
    limit: int = Query(100, ge=1, le=300),
    user: dict = Depends(get_current_user),
):
    from ai.memory.service import list_records

    rows = await list_records(user["id"], q, limit)
    return {"items": [_record_out(r) for r in rows]}


@router.patch("/records/{record_id}")
async def update_record(
    record_id: int,
    req: RecordUpdate,
    user: dict = Depends(get_current_user),
):
    from ai.memory.service import update_record as update

    try:
        row = await update(
            user["id"], record_id, req.content, req.importance, req.state
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if row is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return _record_out(row)


@router.get("/graph")
async def graph(user: dict = Depends(get_current_user)):
    from ai.memory.service import memory_graph

    return await memory_graph(user["id"])


@router.delete("/records/{record_id}")
async def forget_record(record_id: int, user: dict = Depends(get_current_user)):
    from ai.memory.service import forget_record as forget

    ok = await forget(user["id"], record_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"message": "Forgotten"}


@router.post("/consolidate")
async def consolidate_memories(user: dict = Depends(get_current_user)):
    from ai.memory.service import consolidate

    return await consolidate(user["id"])


def _candidate_out(row) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "content": row.content,
        "confidence": row.confidence,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "source_ref": row.source_ref,
        "trust": row.trust,
        "status": row.status,
        "created_at": row.created_at,
    }


def _record_out(row) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "content": row.content,
        "confidence": row.confidence,
        "importance": row.importance,
        "source_type": row.source_type,
        "sources": row.sources,
        "status": row.status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


class EntityMerge(BaseModel):
    into_id: int


@router.post("/entities/{entity_id}/merge")
async def merge_entity(
    entity_id: int,
    req: EntityMerge,
    user: dict = Depends(get_current_user),
):
    from ai.entities.service import merge_entities

    async with async_session() as db:
        try:
            target = await merge_entities(
                db, user["id"], entity_id, req.into_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        await db.commit()
    return {"message": "Entities merged", "target_id": target.id}


@router.delete("/entities/{doc_key}")
async def delete_entity(doc_key: str, user: dict = Depends(get_current_user)):
    """Forget one entity; the underlying source content is untouched."""
    if doc_key.isdigit():
        from ai.entities.models import Entity

        async with async_session() as db:
            entity = await db.get(Entity, int(doc_key))
            if entity is None or entity.user_id != user["id"]:
                raise HTTPException(status_code=404, detail="Entity not found")
            entity.status = "forgotten"
            await db.commit()
        return {"message": "Entity forgotten"}

    if engine.dialect.name != "postgresql":
        raise HTTPException(status_code=404, detail="Entity not found")
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "DELETE FROM embeddings WHERE collection = 'entities' "
                "AND user_id = :uid AND doc_key = :key"
            ),
            {"uid": user["id"], "key": doc_key},
        )
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"message": "Entity forgotten"}

