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
]
