"""Bot-scoped memory: storage, retrieval and prompt context building.

L0 shared facts stay in ``user_profiles``. L1 long-term memory lives in
``bot_memories`` (and is mirrored into the pgvector ``entities`` collection for
semantic retrieval). L2 conversation history lives in ``chat_messages``.
"""

from core.logging import get_logger
log = get_logger(__name__)
import json
import time
import asyncio
from datetime import datetime

from sqlalchemy import select, delete, or_

from core.config.settings import settings
from core.database.session import async_session
from ai.bots.models import Bot, BotMemory


def _loads(value):
    if not value:
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return None


_EXTERNAL_ENTITY_SOURCES = {"sources", "source_item", "rss", "rss_entry", "article"}


def _is_external_entity(meta: dict) -> bool:
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


async def add_memory(
    user_id: int,
    bot_id: int,
    content: str,
    *,
    kind: str = "fact",
    importance: float = 0.5,
    source_run_id: int | None = None,
    expires_at: datetime | None = None,
) -> BotMemory:
    content = (content or "").strip()
    if not content:
        raise ValueError("content is required")

    async with async_session() as db:
        mem = BotMemory(
            bot_id=bot_id,
            user_id=user_id,
            kind=kind,
            content=content[:2000],
            importance=importance,
            source_run_id=source_run_id,
            expires_at=expires_at,
        )
        db.add(mem)
        await db.flush()
        mem_id = mem.id
        await db.commit()
        await db.refresh(mem)

    # Vector mirror is best-effort: the DB row is the source of truth.
    try:
        from ai.llm.embeddings import generate_embedding
        from ai.retrieval import vector_store

        vec = await generate_embedding(content)
        if vec:
            await vector_store.upsert(
                "entities",
                doc_key=f"mem_{bot_id}_{mem_id}",
                user_id=user_id,
                embedding=vec,
                source_type="memory",
                source_id=mem_id,
                title=content[:120],
                content=content[:2000],
                metadata={
                    "type": "memory",
                    "bot_id": bot_id,
                    "kind": kind,
                    "saved_at": datetime.utcnow().isoformat(),
                },
            )
    except Exception as e:
        log.warning(f"[bots.memory] vector mirror failed: {e}")

    return mem


async def list_memories(
    user_id: int, bot_id: int, limit: int = 100, kind: str | None = None
) -> list[BotMemory]:
    async with async_session() as db:
        q = select(BotMemory).where(
            BotMemory.user_id == user_id, BotMemory.bot_id == bot_id
        )
        if kind:
            q = q.where(BotMemory.kind == kind)
        q = q.order_by(BotMemory.importance.desc(), BotMemory.updated_at.desc()).limit(limit)
        return list((await db.execute(q)).scalars().all())


async def delete_memory(user_id: int, bot_id: int, memory_id: int) -> bool:
    async with async_session() as db:
        mem = (
            await db.execute(
                select(BotMemory).where(
                    BotMemory.id == memory_id,
                    BotMemory.bot_id == bot_id,
                    BotMemory.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if mem is None:
            return False
        await db.delete(mem)
        await db.commit()

    try:
        from ai.retrieval import vector_store
        await vector_store.delete("entities", f"mem_{bot_id}_{memory_id}")
    except Exception:
        pass
    return True


async def search_memories(
    user_id: int,
    bot_id: int,
    query: str,
    *,
    limit: int = 5,
    include_legacy: bool = False,
    vec: list[float] | None = None,
) -> list[dict]:
    """Return memory dicts with ``content`` + ``kind``.

    Combines recent high-importance DB rows with semantic hits, so memory still
    works when embeddings are unavailable.
    """
    out: list[dict] = []
    seen: set[str] = set()
    db_limit = limit if not query else max(1, limit // 2)

    try:
        async with async_session() as db:
            now = datetime.utcnow()
            rows = (
                await db.execute(
                    select(BotMemory)
                    .where(
                        BotMemory.user_id == user_id,
                        BotMemory.bot_id == bot_id,
                        or_(BotMemory.expires_at.is_(None), BotMemory.expires_at > now),
                    )
                    .order_by(BotMemory.importance.desc(), BotMemory.updated_at.desc())
                    .limit(db_limit)
                )
            ).scalars().all()
            for m in rows:
                key = m.content.strip()
                if key and key not in seen:
                    seen.add(key)
                    out.append({"content": m.content, "kind": m.kind})
    except Exception:
        pass

    if query and settings.memory_layer_enabled:
        try:
            from ai.llm.embeddings import generate_embedding
            from ai.retrieval import vector_store

            if vec is None:
                vec = await generate_embedding(query)
            if vec:
                hits = await vector_store.search(
                    "entities", user_id, vec, limit=max(limit * 4, 12)
                )
                for h in hits:
                    meta = h.get("metadata") or {}
                    if meta.get("type") != "memory":
                        continue
                    hit_bot = meta.get("bot_id")
                    if hit_bot != bot_id and not (include_legacy and hit_bot is None):
                        continue
                    content = (h.get("content") or h.get("title") or "").strip()
                    if content and content not in seen:
                        seen.add(content)
                        out.append({"content": content, "kind": meta.get("kind") or "fact"})
                    if len(out) >= limit:
                        break
        except Exception:
            pass

    return out[:limit]


async def _profile_block(user_id: int) -> str | None:
    try:
        from core.auth.domain.models import UserProfile

        async with async_session() as db:
            p = (
                await db.execute(
                    select(UserProfile).where(UserProfile.user_id == user_id)
                )
            ).scalar_one_or_none()
            if p is None:
                return None

            info = []
            if p.name:
                info.append(f"姓名: {p.name}")
            if p.role:
                info.append(f"角色: {p.role}")
            if p.company:
                info.append(f"公司: {p.company}")
            contacts = _loads(p.contacts)
            if contacts:
                info.append(
                    "联系�? "
                    + "; ".join(
                        f'{c.get("name", "")}({c.get("relation", "")})'
                        for c in contacts
                        if isinstance(c, dict)
                    )
                )
            projects = _loads(p.projects)
            if projects:
                info.append(
                    "项目: "
                    + "; ".join(
                        f'{x.get("name", "")}({x.get("deadline", "")})'
                        for x in projects
                        if isinstance(x, dict)
                    )
                )
            dev = _loads(p.developer)
            if dev:
                parts = []
                for key, label in (
                    ("github_username", "GitHub"),
                    ("github_email", "Git 邮箱"),
                    ("default_org", "默认组织"),
                    ("default_branch", "默认分支"),
                    ("commit_style", "提交规范"),
                ):
                    if dev.get(key):
                        parts.append(f"{label}: {dev[key]}")
                if dev.get("permissions"):
                    parts.append("代码权限: " + ", ".join(dev["permissions"]))
                if dev.get("workspace_roots"):
                    parts.append("工作�? " + ", ".join(dev["workspace_roots"]))
                if parts:
                    info.append("开发者档�? " + "; ".join(parts))

            return "【用户信息】\n" + "\n".join(info) if info else None
    except Exception:
        return None


async def _insight_block(user_id: int) -> str | None:
    """Recent daily reviews, so the assistant remembers what just happened."""
    try:
        from ai.insights.daily import build_insight_context

        return await build_insight_context(user_id, days=2)
    except Exception:
        return None


async def _long_term_memory_block(
    user_id: int, query: str, vec: list[float] | None = None
) -> str | None:
    try:
        from ai.memory.service import build_memory_context

        return await build_memory_context(user_id, query, limit=8, vec=vec)
    except Exception:
        return None


async def build_bot_context(
    user_id: int, bot: Bot | None = None, query: str = "", timing: dict | None = None
) -> str | None:
    """Compose the bot's context block: shared facts + bot memory + entities.

    The three memory lookups all need an embedding of the same query.  Compute
    it once and run the vector searches concurrently: doing this serially used
    to add ~1.8s to every voice turn.
    """
    parts: list[str] = []

    t = time.monotonic()
    profile = await _profile_block(user_id)
    if timing is not None:
        timing["profile"] = time.monotonic() - t
    if profile:
        parts.append(profile)

    t = time.monotonic()
    insight = await _insight_block(user_id)
    if timing is not None:
        timing["insight"] = time.monotonic() - t
    if insight:
        parts.append(insight)

    vec = None
    if query and settings.memory_layer_enabled:
        t = time.monotonic()
        try:
            from ai.llm.embeddings import generate_embedding

            vec = await generate_embedding(query)
        except Exception:
            vec = None
        if timing is not None:
            timing["embedding"] = time.monotonic() - t

    t = time.monotonic()
    if bot is not None:
        memories_coro = search_memories(
            user_id, bot.id, query, include_legacy=bool(bot.is_default), vec=vec
        )
    else:
        memories_coro = _legacy_memories(user_id, query, vec=vec)
    long_term, memories, entities = await asyncio.gather(
        _long_term_memory_block(user_id, query, vec=vec),
        memories_coro,
        _entities_block(user_id, query, vec=vec),
    )
    if timing is not None:
        timing["memory_lookup"] = time.monotonic() - t

    if long_term:
        parts.append(long_term)
    if memories:
        lines = [f"- {m['content']}" for m in memories]
        parts.append("【本 Bot 的记忆】\n" + "\n".join(lines))
    if entities:
        parts.append(entities)

    return "\n\n".join(parts) if parts else None


async def _graph_entities_block(user_id: int, query: str) -> str | None:
    """Entities and typed relations expanded from the canonical graph."""
    if not (query and settings.memory_layer_enabled):
        return None
    try:
        from ai.entities.service import graph_context
        from core.database.session import async_session

        async with async_session() as db:
            context = await graph_context(db, user_id, query)
        entities = context.get("entities") or []
        if not entities:
            return None
        lines = ["【相关实体】"]
        for entity in entities[:8]:
            lines.append(f"- {entity['name']} ({entity['type']})")
        relations = context.get("relations") or []
        if relations:
            labels = {
                "works_on": "负责", "assigned_to": "负责", "member_of": "属于",
                "owns": "拥有", "uses": "使用", "about": "关于",
                "communicates_with": "沟通", "knows": "认识",
                "related_to": "相关", "同一来源": "同一来源",
            }
            lines.append("【实体关系】")
            for relation in relations[:10]:
                label = labels.get(relation["relation"], relation["relation"])
                lines.append(
                    f"- {relation['from_name']} --{label}--> "
                    f"{relation['to_name']}"
                )
        mentions = context.get("mentions") or []
        if mentions:
            lines.append("【相关来源】")
            seen = set()
            for mention in mentions:
                key = (mention.get("source_type"), mention.get("source_id"))
                if key in seen:
                    continue
                seen.add(key)
                quote = str(mention.get("quote") or "").strip()
                lines.append(
                    f"- {mention.get('source_type')} #{mention.get('source_id')}"
                    + (f": {quote[:120]}" if quote else "")
                )
                if len(seen) >= 8:
                    break
        return "\n".join(lines)
    except Exception:
        return None


async def _entities_block(user_id: int, query: str, vec: list[float] | None = None) -> str | None:
    """Non-memory entities (people, projects, files...) related to the query."""
    if not (query and settings.memory_layer_enabled):
        return None
    graph_block = await _graph_entities_block(user_id, query)
    if graph_block:
        return graph_block
    try:
        from ai.llm.embeddings import generate_embedding
        from ai.retrieval import vector_store

        if vec is None:
            vec = await generate_embedding(query)
        if not vec:
            return None
        hits = await vector_store.search("entities", user_id, vec, limit=8)
        related = []
        for h in hits:
            meta = h.get("metadata") or {}
            if meta.get("type") == "memory":
                continue
            if _is_external_entity(meta):
                continue
            title = h.get("title") or ""
            if not title:
                continue
            related.append(f"{title}({meta.get('type', '')})")
        if related:
            return "【相关实体】\n" + ", ".join(related[:5])
    except Exception:
        pass
    return None


async def _legacy_memories(
    user_id: int, query: str, limit: int = 5, vec: list[float] | None = None
) -> list[dict]:
    """Pre-bot memories stored without a bot_id (read-compatible path)."""
    if not (query and settings.memory_layer_enabled):
        return []
    try:
        from ai.llm.embeddings import generate_embedding
        from ai.retrieval import vector_store

        if vec is None:
            vec = await generate_embedding(query)
        if not vec:
            return []
        hits = await vector_store.search("entities", user_id, vec, limit=limit * 2)
        out = []
        for h in hits:
            meta = h.get("metadata") or {}
            if meta.get("type") != "memory" or meta.get("bot_id") is not None:
                continue
            content = (h.get("content") or h.get("title") or "").strip()
            if content:
                out.append({"content": content, "kind": meta.get("kind") or "fact"})
        return out[:limit]
    except Exception:
        return []

