"""Memory OS 2.0 services: extraction, review, consolidation and context injection."""

from __future__ import annotations

from core.logging import get_logger
log = get_logger(__name__)
from ai.llm.usage import tracked_create

import json
import re
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update

from core.config.settings import settings
from core.database.session import async_session
from ai.memory.models import MemoryCandidate, MemoryEdge, MemoryRecord

MAX_CANDIDATES_PER_TEXT = 8
MAX_RECORD_CONTENT = 1200


def _normalize(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[，。！？；：、,.!?;:]+$", "", text)
    return text[:600]


def _loads(value):
    if isinstance(value, (list, dict)):
        return value
    if not value:
        return []
    try:
        return json.loads(value)
    except Exception:
        return []


async def queue_candidate(
    db,
    user_id: int,
    kind: str,
    content: str,
    *,
    confidence: int = 60,
    source_type: str = "chat",
    source_id: int | None = None,
    source_ref: dict | None = None,
    trust: str = "trusted",
    bot_id: int | None = None,
) -> MemoryCandidate | None:
    content = (content or "").strip()
    norm = _normalize(content)
    if len(norm) < 6:
        return None
    kind = kind if kind in ("fact", "preference", "commitment", "relationship", "project") else "fact"
    confidence = max(0, min(int(confidence), 100))

    existing_record = (await db.execute(
        select(MemoryRecord).where(
            MemoryRecord.user_id == user_id,
            MemoryRecord.normalized == norm,
            MemoryRecord.kind == kind,
            MemoryRecord.status == "active",
        )
    )).scalar_one_or_none()
    if existing_record is not None:
        return None

    existing = (await db.execute(
        select(MemoryCandidate).where(
            MemoryCandidate.user_id == user_id,
            MemoryCandidate.normalized == norm,
            MemoryCandidate.kind == kind,
            MemoryCandidate.status == "pending",
        )
    )).scalar_one_or_none()
    if existing is not None:
        existing.confidence = max(existing.confidence or 0, confidence)
        existing.trust = "trusted" if existing.trust == "trusted" or trust == "trusted" else "untrusted"
        sources = _loads(existing.source_ref)
        if source_ref:
            sources.append(source_ref)
        existing.source_ref = sources[-20:]
        await db.flush()
        return existing

    row = MemoryCandidate(
        user_id=user_id,
        bot_id=bot_id,
        kind=kind,
        content=content[:MAX_RECORD_CONTENT],
        normalized=norm,
        confidence=confidence,
        source_type=source_type,
        source_id=source_id,
        source_ref=[source_ref] if source_ref else None,
        trust=trust,
        status="pending",
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def _llm_extract(text: str) -> list[dict]:
    if not settings.llm_api_key or not (text or "").strip():
        return []
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        resp = await tracked_create(client, 
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": (
                    "你是长期记忆抽取器。只抽取值得跨会话保留的稳定信息："
                    "用户的事实、偏好、承诺/截止、重要关系、项目。"
                    "不要抽取一次性操作、闲聊、临时状态、模型自己的猜测。"
                    "每条 content 必须自含（不要用“他/这个”指代），最多 8 条。"
                    "只返回 JSON: {\"memories\":[{\"kind\":\"fact|preference|commitment|relationship|project\","
                    "\"content\":\"...\",\"confidence\":0-100}]}。不要输出其他内容。"
                )},
                {"role": "user", "content": text[:12000]},
            ],
            temperature=0.1,
        )
        raw = resp.choices[0].message.content or ""
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return []
        data = json.loads(m.group(0))
        items = data.get("memories") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []
        out = []
        for item in items[:MAX_CANDIDATES_PER_TEXT]:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if len(content) < 6:
                continue
            out.append({
                "kind": str(item.get("kind") or "fact"),
                "content": content,
                "confidence": int(item.get("confidence") or 60),
            })
        return out
    except Exception as e:
        log.warning(f"[memory] extract error: {e}")
        return []


async def ingest_text(
    user_id: int,
    text: str,
    *,
    source_type: str = "chat",
    source_id: int | None = None,
    source_ref: dict | None = None,
    trust: str = "trusted",
    bot_id: int | None = None,
) -> int:
    items = await _llm_extract(text)
    if not items:
        return 0
    count = 0
    async with async_session() as db:
        for item in items:
            row = await queue_candidate(
                db, user_id, item["kind"], item["content"],
                confidence=item["confidence"],
                source_type=source_type,
                source_id=source_id,
                source_ref=source_ref,
                trust=trust,
                bot_id=bot_id,
            )
            if row is not None:
                count += 1
        await db.commit()
    return count


async def list_candidates(user_id: int, status: str = "pending", limit: int = 100):
    async with async_session() as db:
        q = select(MemoryCandidate).where(MemoryCandidate.user_id == user_id)
        if status and status != "all":
            q = q.where(MemoryCandidate.status == status)
        rows = list((await db.execute(
            q.order_by(MemoryCandidate.id.desc()).limit(max(1, min(limit, 300)))
        )).scalars().all())
    return rows


async def _link_edges(db, user_id: int, record: MemoryRecord) -> None:
    """Link a memory to profile contacts/projects it mentions."""
    try:
        from core.auth.domain.models import UserProfile

        profile = (await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )).scalar_one_or_none()
        if profile is None:
            return
        targets: list[tuple[str, str, int | None]] = []
        for c in _loads(profile.contacts) or []:
            if isinstance(c, dict) and c.get("name"):
                targets.append(("person", str(c["name"]), None))
        for p in _loads(profile.projects) or []:
            if isinstance(p, dict) and p.get("name"):
                targets.append(("project", str(p["name"]), None))
        if not targets:
            return
        existing = {
            e.target_name for e in (await db.execute(
                select(MemoryEdge).where(
                    MemoryEdge.user_id == user_id,
                    MemoryEdge.memory_id == record.id,
                )
            )).scalars().all()
        }
        for target_type, name, target_id in targets:
            if name and name in (record.content or "") and name not in existing:
                db.add(MemoryEdge(
                    user_id=user_id,
                    memory_id=record.id,
                    target_type=target_type,
                    target_id=target_id,
                    target_name=name,
                    relation="mentions",
                ))
                existing.add(name)
    except Exception as e:
        log.warning(f"[memory] edge error: {e}")


async def _supersede_conflicts(db, user_id: int, candidate: MemoryCandidate, new_record_id: int) -> list[int]:
    """Mark older records superseded when the new memory clearly replaces them."""
    old_rows = list((await db.execute(
        select(MemoryRecord).where(
            MemoryRecord.user_id == user_id,
            MemoryRecord.kind == candidate.kind,
            MemoryRecord.status == "active",
            MemoryRecord.id != new_record_id,
        )
    )).scalars().all())
    superseded: list[int] = []
    new_content = candidate.content or ""
    for old in old_rows:
        old_content = old.content or ""
        if len(old_content) < 6 or len(new_content) < 6:
            continue
        # Only a strictly more specific new memory supersedes the old one.
        # The reverse (new is a shorter summary) must not retire richer facts.
        if old_content in new_content and old_content != new_content:
            old.status = "superseded"
            old.valid_to = datetime.utcnow()
            old.superseded_by = new_record_id
            superseded.append(old.id)
    return superseded


async def _index_record(user_id: int, record: MemoryRecord) -> None:
    if not _vector_backend_available():
        return
    try:
        from ai.retrieval.indexer import index_content

        await index_content(
            user_id,
            "memory",
            record.id,
            f"[{record.kind}] {record.content[:60]}",
            record.content,
            metadata={"kind": record.kind, "link": "/memory"},
        )
    except Exception as e:
        log.warning(f"[memory] index error: {e}")


def _vector_backend_available() -> bool:
    """Vector recall is pgvector-only; skip the embedding call elsewhere."""
    try:
        from core.config.settings import settings as _settings
        from core.database.session import engine

        return bool(_settings.data_layer_enabled) and engine.dialect.name == "postgresql"
    except Exception:
        return False


async def approve_candidate(user_id: int, candidate_id: int) -> MemoryRecord | None:
    async with async_session() as db:
        cand = (await db.execute(
            select(MemoryCandidate).where(
                MemoryCandidate.id == candidate_id,
                MemoryCandidate.user_id == user_id,
            )
        )).scalar_one_or_none()
        if cand is None or cand.status != "pending":
            return None
        record = (await db.execute(
            select(MemoryRecord).where(
                MemoryRecord.user_id == user_id,
                MemoryRecord.normalized == cand.normalized,
                MemoryRecord.kind == cand.kind,
            )
        )).scalar_one_or_none()
        if record is not None and record.status != "active":
            # Explicitly re-approving a superseded memory swaps the supersede
            # direction instead of leaving two contradictory active rows.
            if record.status == "superseded" and record.superseded_by:
                superseder = (await db.execute(
                    select(MemoryRecord).where(
                        MemoryRecord.id == record.superseded_by,
                        MemoryRecord.user_id == user_id,
                    )
                )).scalar_one_or_none()
                if superseder is not None and superseder.status == "active":
                    superseder.status = "superseded"
                    superseder.valid_to = datetime.utcnow()
                    superseder.superseded_by = record.id
            record.status = "active"
            record.valid_to = None
            record.superseded_by = None
        if record is None:
            record = MemoryRecord(
                user_id=user_id,
                bot_id=cand.bot_id,
                kind=cand.kind,
                content=cand.content,
                normalized=cand.normalized,
                confidence=cand.confidence,
                importance=max(40, cand.confidence),
                source_type=cand.source_type,
                source_id=cand.source_id,
                sources=_loads(cand.source_ref),
                status="active",
                valid_from=datetime.utcnow(),
            )
            db.add(record)
            await db.flush()
            await db.refresh(record)
        else:
            record.confidence = max(record.confidence or 0, cand.confidence or 0)
            sources = _loads(record.sources)
            sources.extend(_loads(cand.source_ref))
            record.sources = sources[-20:]
        await _supersede_conflicts(db, user_id, cand, record.id)
        await _link_edges(db, user_id, record)
        cand.status = "approved"
        cand.reviewed_at = datetime.utcnow()
        await db.commit()
        await _index_record(user_id, record)
        return record


async def reject_candidate(user_id: int, candidate_id: int, reason: str | None = None) -> bool:
    async with async_session() as db:
        cand = (await db.execute(
            select(MemoryCandidate).where(
                MemoryCandidate.id == candidate_id,
                MemoryCandidate.user_id == user_id,
            )
        )).scalar_one_or_none()
        if cand is None or cand.status != "pending":
            return False
        cand.status = "rejected"
        cand.reason = reason
        cand.reviewed_at = datetime.utcnow()
        await db.commit()
        return True


async def consolidate(user_id: int, auto_approve_threshold: int = 90) -> dict:
    """Auto-approve high-confidence trusted candidates; leave the rest for review."""
    candidates = await list_candidates(user_id, "pending", 300)
    approved = 0
    for cand in candidates:
        if cand.trust == "trusted" and (cand.confidence or 0) >= auto_approve_threshold:
            if await approve_candidate(user_id, cand.id):
                approved += 1
    return {"pending": len(candidates), "auto_approved": approved}


async def list_records(user_id: int, query: str = "", limit: int = 100):
    async with async_session() as db:
        q = select(MemoryRecord).where(
            MemoryRecord.user_id == user_id,
            MemoryRecord.status == "active",
        )
        if query:
            like = f"%{query}%"
            q = q.where(MemoryRecord.content.ilike(like))
        rows = list((await db.execute(
            q.order_by(MemoryRecord.importance.desc(), MemoryRecord.updated_at.desc())
            .limit(max(1, min(limit, 300)))
        )).scalars().all())
    return rows


async def forget_record(user_id: int, record_id: int) -> bool:
    async with async_session() as db:
        row = (await db.execute(
            select(MemoryRecord).where(
                MemoryRecord.id == record_id,
                MemoryRecord.user_id == user_id,
            )
        )).scalar_one_or_none()
        if row is None:
            return False
        row.status = "deleted"
        row.valid_to = datetime.utcnow()
        await db.commit()
    try:
        from ai.retrieval import vector_store

        await vector_store.delete_source(user_id, "memory", record_id)
    except Exception:
        pass
    return True


async def update_record(
    user_id: int, record_id: int, content: str | None = None,
    importance: int | None = None,
) -> MemoryRecord | None:
    async with async_session() as db:
        row = (await db.execute(
            select(MemoryRecord).where(
                MemoryRecord.id == record_id,
                MemoryRecord.user_id == user_id,
            )
        )).scalar_one_or_none()
        if row is None or row.status != "active":
            return None
        if content and content.strip():
            new_content = content.strip()[:MAX_RECORD_CONTENT]
            new_norm = _normalize(new_content)
            clash = (await db.execute(
                select(MemoryRecord).where(
                    MemoryRecord.user_id == user_id,
                    MemoryRecord.normalized == new_norm,
                    MemoryRecord.kind == row.kind,
                    MemoryRecord.id != record_id,
                )
            )).scalar_one_or_none()
            if clash is not None:
                raise ValueError("A memory with the same content already exists")
            row.content = new_content
            row.normalized = new_norm
        if importance is not None:
            row.importance = max(0, min(int(importance), 100))
        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise ValueError("Unable to update memory") from e
        await db.refresh(row)

    # Content may mention different people/projects now: rebuild edges.
    async with async_session() as db:
        await db.execute(delete(MemoryEdge).where(
            MemoryEdge.user_id == user_id,
            MemoryEdge.memory_id == record_id,
        ))
        await _link_edges(db, user_id, row)
        await db.commit()
    await _index_record(user_id, row)
    return row


async def _vector_records(
    user_id: int, query: str, limit: int, vec: list[float] | None = None
) -> list[MemoryRecord]:
    if not _vector_backend_available():
        return []
    from ai.llm.embeddings import generate_embedding
    from ai.retrieval import vector_store

    if vec is None:
        vec = await generate_embedding(query)
    if not vec:
        return []
    hits = await vector_store.search(
        "omnidocs", user_id, vec, limit=max(4, limit * 2), source_types=["memory"]
    )
    ids = [h.get("source_id") for h in hits if h.get("source_id")]
    if not ids:
        return []
    async with async_session() as db:
        rows = list((await db.execute(
            select(MemoryRecord).where(
                MemoryRecord.user_id == user_id,
                MemoryRecord.id.in_(ids),
                MemoryRecord.status == "active",
            )
        )).scalars().all())
    order = {rid: i for i, rid in enumerate(ids)}
    rows.sort(key=lambda r: order.get(r.id, 999))
    return rows[:limit]


async def _touch_records(user_id: int, ids: list[int]) -> None:
    if not ids:
        return
    try:
        async with async_session() as db:
            await db.execute(
                update(MemoryRecord)
                .where(
                    MemoryRecord.user_id == user_id,
                    MemoryRecord.id.in_(ids),
                )
                .values(use_count=MemoryRecord.use_count + 1, last_used_at=datetime.utcnow())
            )
            await db.commit()
    except Exception:
        pass


async def build_memory_context(
    user_id: int, query: str | None = None, limit: int = 8,
    vec: list[float] | None = None,
) -> str | None:
    try:
        rows: list[MemoryRecord] = []
        if query:
            try:
                rows = await _vector_records(user_id, query, limit, vec=vec)
            except Exception:
                rows = []
        if not rows:
            rows = await list_records(user_id, query or "", limit)
        if not rows and query:
            rows = await list_records(user_id, "", limit)
        if not rows:
            return None
        await _touch_records(user_id, [r.id for r in rows[:limit]])
        lines = []
        for r in rows[:limit]:
            origin = "" if (r.source_type or "chat") in ("chat", "manual") else f"/{r.source_type}"
            lines.append(f"- [{r.kind}{origin}] {r.content}")
        return ("【长期记忆】\n" + "\n".join(lines))[:1600]
    except Exception:
        return None


async def memory_graph(user_id: int, limit: int = 100) -> dict:
    async with async_session() as db:
        records = list((await db.execute(
            select(MemoryRecord).where(
                MemoryRecord.user_id == user_id,
                MemoryRecord.status == "active",
            ).order_by(MemoryRecord.importance.desc()).limit(max(1, min(limit, 300)))
        )).scalars().all())
        ids = [r.id for r in records]
        edges = list((await db.execute(
            select(MemoryEdge).where(
                MemoryEdge.user_id == user_id,
                MemoryEdge.memory_id.in_(ids or [0]),
            )
        )).scalars().all())
        # Backfill edges for memories created before the graph feature existed.
        linked = {e.memory_id for e in edges}
        missing = [r for r in records if r.id not in linked]
        if missing:
            for r in missing[:25]:
                await _link_edges(db, user_id, r)
            await db.commit()
            edges = list((await db.execute(
                select(MemoryEdge).where(
                    MemoryEdge.user_id == user_id,
                    MemoryEdge.memory_id.in_(ids or [0]),
                )
            )).scalars().all())
    nodes = [
        {"id": f"memory:{r.id}", "type": "memory", "label": r.content[:80], "kind": r.kind}
        for r in records
    ]
    seen: set[str] = set()
    edges_out: list[dict] = []
    edge_seen: set[tuple[int, str, str]] = set()
    for e in edges:
        key = f"{e.target_type}:{e.target_name}"
        if key not in seen:
            seen.add(key)
            nodes.append({"id": key, "type": e.target_type, "label": e.target_name})
        edge_key = (e.memory_id, e.target_type, e.target_name)
        if edge_key in edge_seen:
            continue
        edge_seen.add(edge_key)
        edges_out.append({
            "source": f"memory:{e.memory_id}",
            "target": key,
            "relation": e.relation,
        })
    return {"nodes": nodes, "edges": edges_out}
