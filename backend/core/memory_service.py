"""Memory OS 2.0 services: extraction, review, consolidation and context injection."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from sqlalchemy import select, update

from core.config.settings import settings
from core.database.session import async_session
from core.memory_models import MemoryCandidate, MemoryEdge, MemoryRecord

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
        resp = await client.chat.completions.create(
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
        print(f"[memory] extract error: {e}")
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


async def ingest_recent_chats(user_id: int, hours: int = 24) -> int:
    """Extract long-term memories from the user's recent chat messages."""
    from plugins.chat.backend.models import ChatMessage

    since = datetime.utcnow() - timedelta(hours=max(1, hours))
    async with async_session() as db:
        rows = list((await db.execute(
            select(ChatMessage).where(
                ChatMessage.user_id == user_id,
                ChatMessage.created_at >= since,
            ).order_by(ChatMessage.id).limit(300)
        )).scalars().all())
    if not rows:
        return 0
    lines = []
    for m in rows:
        # Only user-authored text is trusted for long-term memory; assistant
        # output may contain hallucinations and must not become a "fact".
        if m.role != "user":
            continue
        lines.append(f"用户: {(m.content or '')[:800]}")
    text = "\n".join(lines)[-16000:]
    return await ingest_text(
        user_id,
        text,
        source_type="chat",
        source_id=rows[-1].id,
        source_ref={"session_id": rows[-1].session_id, "message_id": rows[-1].id},
        trust="trusted",
    )


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
        print(f"[memory] edge error: {e}")


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
        if old_content in new_content or new_content in old_content:
            old.status = "superseded"
            old.valid_to = datetime.utcnow()
            old.superseded_by = new_record_id
            superseded.append(old.id)
    return superseded


async def _index_record(user_id: int, record: MemoryRecord) -> None:
    try:
        from core.ai.indexer import index_content

        await index_content(
            user_id,
            "memory",
            record.id,
            f"[{record.kind}] {record.content[:60]}",
            record.content,
            metadata={"kind": record.kind, "link": "/about"},
        )
    except Exception as e:
        print(f"[memory] index error: {e}")


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
        created = record is None
        if record is not None and record.status != "active":
            record.status = "active"
            record.valid_to = None
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
        if created:
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
        from core.ai import vector_store

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
        if row is None:
            return None
        if content and content.strip():
            row.content = content.strip()[:MAX_RECORD_CONTENT]
            row.normalized = _normalize(content)
        if importance is not None:
            row.importance = max(0, min(int(importance), 100))
        await db.commit()
        await db.refresh(row)
    await _index_record(user_id, row)
    return row


async def _vector_records(user_id: int, query: str, limit: int) -> list[MemoryRecord]:
    from core.ai.embeddings import generate_embedding
    from core.ai import vector_store

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


async def _touch_records(ids: list[int]) -> None:
    if not ids:
        return
    try:
        async with async_session() as db:
            await db.execute(
                update(MemoryRecord)
                .where(MemoryRecord.id.in_(ids))
                .values(use_count=MemoryRecord.use_count + 1, last_used_at=datetime.utcnow())
            )
            await db.commit()
    except Exception:
        pass


async def build_memory_context(user_id: int, query: str | None = None, limit: int = 8) -> str | None:
    try:
        rows: list[MemoryRecord] = []
        if query:
            try:
                rows = await _vector_records(user_id, query, limit)
            except Exception:
                rows = []
        if not rows:
            rows = await list_records(user_id, query or "", limit)
        if not rows and query:
            rows = await list_records(user_id, "", limit)
        if not rows:
            return None
        await _touch_records([r.id for r in rows[:limit]])
        lines = [f"- [{r.kind}] {r.content}" for r in rows[:limit]]
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
    nodes = [
        {"id": f"memory:{r.id}", "type": "memory", "label": r.content[:80], "kind": r.kind}
        for r in records
    ]
    seen: set[str] = set()
    for e in edges:
        key = f"{e.target_type}:{e.target_name}"
        if key not in seen:
            seen.add(key)
            nodes.append({"id": key, "type": e.target_type, "label": e.target_name})
    return {
        "nodes": nodes,
        "edges": [
            {
                "source": f"memory:{e.memory_id}",
                "target": f"{e.target_type}:{e.target_name}",
                "relation": e.relation,
            }
            for e in edges
        ],
    }
