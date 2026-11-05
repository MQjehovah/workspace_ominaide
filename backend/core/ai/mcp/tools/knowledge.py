"""Knowledge/memory agent tools: RAG over the omnidocs collection and
persistent "remember this" facts stored in the entities collection.

- search_knowledge: lets the agent actively retrieve the user's indexed
  content (notes, files, mail, schedule, RSS) instead of guessing.
- save_memory: lets the agent persist facts the user asks it to remember
  ("记住我家服务器是…"); build_context auto-injects matching memories.
"""
import hashlib

from core.ai.mcp.core import MCPTool, MCPCallResponse, MCPContent
from core.config.settings import settings


def _ok(text: str) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=text)])


def _err(text: str) -> MCPCallResponse:
    return MCPCallResponse(isError=True, content=[MCPContent(text=text)])


def _snippet(text: str | None, width: int = 220) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    return text[:width] + ("…" if len(text) > width else "")


async def propose_memory(user_id: int, args: dict) -> MCPCallResponse:
    """Queue review candidates from the model's own analysis (no second LLM call)."""
    items = args.get("items")
    if not isinstance(items, list) or not items:
        return _err("items is required")
    source_type = str(args.get("source_type") or "chat")[:32]
    source_id = args.get("source_id")
    try:
        source_id = int(source_id) if source_id is not None else None
    except (TypeError, ValueError):
        source_id = None
    source_ref = args.get("source_ref") if isinstance(args.get("source_ref"), dict) else None
    # External content is never auto-approved; it goes to the review queue.
    trust = "untrusted" if source_type in ("email", "dingtalk", "rss", "external") else "trusted"

    from core.bots.context import get_current_bot_id
    from core.database.session import async_session
    from core.memory_service import queue_candidate

    bot_id = get_current_bot_id()
    created = 0
    async with async_session() as db:
        for item in items[:8]:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if len(content) < 6:
                continue
            try:
                confidence = int(item.get("confidence") or 60)
            except (TypeError, ValueError):
                confidence = 60
            row = await queue_candidate(
                db, user_id,
                str(item.get("kind") or "fact"),
                content,
                confidence=confidence,
                source_type=source_type,
                source_id=source_id,
                source_ref=source_ref,
                trust=trust,
                bot_id=bot_id,
            )
            if row is not None:
                created += 1
        await db.commit()
    return _ok(f"已提交 {created} 条候选记忆，等待用户审核")


async def search_knowledge(user_id: int, args: dict) -> MCPCallResponse:
    """Vector search over everything indexed for the user (omnidocs)."""
    query = (args.get("query") or "").strip()
    limit = min(int(args.get("limit") or 5), 10)
    if not query:
        return _err("query is required")
    if not settings.data_layer_enabled:
        return _err("data layer disabled")

    try:
        from core.ai.embeddings import generate_embedding
        from core.ai import vector_store

        vec = await generate_embedding(query)
        if not vec:
            return _err("embedding unavailable")
        hits = await vector_store.search("omnidocs", user_id, vec, limit=limit)
    except Exception as e:
        return _err(f"search failed: {e}")

    if not hits:
        return _ok("知识库中没有相关内容。")

    lines = [f"共 {len(hits)} 条相关内容："]
    for i, h in enumerate(hits, 1):
        stype = h.get("source_type") or "doc"
        lines.append(
            f"{i}. [{stype}] {h.get('title', '')}（相关度 {h.get('score', 0):.2f}）\n"
            f"   {_snippet(h.get('content'))}"
        )
    return _ok("\n".join(lines))


async def save_memory(user_id: int, args: dict) -> MCPCallResponse:
    """Persist a user fact so future conversations know it (auto-injected
    into context when relevant). Scoped to the current bot when available."""
    fact = (args.get("fact") or "").strip()
    if not fact:
        return _err("fact is required")
    if len(fact) > 500:
        fact = fact[:500]
    if not settings.memory_layer_enabled:
        return _err("memory layer disabled")

    from core.bots.context import get_current_bot_id

    bot_id = get_current_bot_id()
    if bot_id is not None:
        try:
            from core.bots.memory import add_memory

            await add_memory(user_id, bot_id, fact)
            return _ok(f"已记住：{fact}")
        except Exception as e:
            return _err(f"save failed: {e}")

    # Legacy path: no bot scope (e.g. direct MCP call). Kept for compatibility.
    try:
        from core.ai.embeddings import generate_embedding
        from core.ai import vector_store
        from datetime import datetime

        vec = await generate_embedding(fact)
        if not vec:
            return _err("embedding unavailable")

        # 同一事实重复保存 → 覆盖（天然去重）
        doc_key = f"mem_{hashlib.md5(fact.encode('utf-8')).hexdigest()[:12]}_{user_id}"
        await vector_store.upsert(
            "entities",
            doc_key=doc_key,
            user_id=user_id,
            embedding=vec,
            source_type="memory",
            source_id=None,
            title=fact[:80],
            content=fact,
            metadata={"type": "memory", "saved_at": datetime.utcnow().isoformat()},
        )
        return _ok(f"已记住：{fact}")
    except Exception as e:
        return _err(f"save failed: {e}")


TOOLS = [
    (
        MCPTool(
            name="search_knowledge",
            description=(
                "检索用户的个人知识库（笔记、文件、邮件、日程、RSS 均已自动索引）。"
                "回答涉及用户背景的问题（网络布局、服务器、项目细节、历史决定等）时，"
                "先调用本工具检索，不要凭空猜测。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "语义检索关键词"},
                    "limit": {"type": "integer", "description": "返回条数，默认 5"},
                },
                "required": ["query"],
            },
        ),
        search_knowledge,
    ),
    (
        MCPTool(
            name="save_memory",
            description=(
                "把用户要求记住的长期事实存入记忆（如家庭网络布局、服务器地址、"
                "项目背景、个人偏好）。用户说\"记住…\"时调用。相关话题的后续对话会自动带上这些事实。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "fact": {"type": "string", "description": "一条独立、自含的事实陈述"},
                },
                "required": ["fact"],
            },
        ),
        save_memory,
    ),
    (
        MCPTool(
            name="propose_memory",
            description=(
                "提交待审核的长期记忆候选（不直接生效）。分析邮件、对话等外部内容时，"
                "把值得跨会话保留的事实/偏好/承诺/项目提交到这里，由用户确认。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "kind": {
                                    "type": "string",
                                    "enum": ["fact", "preference", "commitment", "relationship", "project"],
                                },
                                "content": {"type": "string", "description": "自含的一条记忆，不要用代词"},
                                "confidence": {"type": "integer", "description": "0-100"},
                            },
                            "required": ["content"],
                        },
                        "description": "最多 8 条",
                    },
                    "source_type": {"type": "string", "description": "email/chat/dingtalk/rss"},
                    "source_id": {"type": "integer", "description": "来源对象 id（如邮件 id）"},
                },
                "required": ["items"],
            },
        ),
        propose_memory,
    ),
]
