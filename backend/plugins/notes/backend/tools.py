"""MCP tools for the notes plugin (RAG search + cited Q&A)."""
import json

from ai.mcp.core import MCPCallResponse, MCPContent
from ai.mcp.tools.plugin_tools import register_plugin_tool_handler


def _resp(payload: dict, is_error: bool = False) -> MCPCallResponse:
    return MCPCallResponse(
        isError=is_error,
        content=[MCPContent(text=json.dumps(payload, ensure_ascii=False))],
    )


async def ask_notes(user_id: int, args: dict) -> MCPCallResponse:
    question = (args.get("question") or "").strip()
    if not question:
        return _resp({"ok": False, "detail": "question is required"}, True)
    from core.database.session import async_session
    from plugins.notes.backend.rag import ask_notes as _ask, ensure_indexed
    try:
        await ensure_indexed(user_id)
        async with async_session() as db:
            result = await _ask(db, user_id, question)
        return _resp({"ok": True, **result})
    except Exception as e:
        return _resp({"ok": False, "detail": str(e)}, True)


async def search_notes_semantic(user_id: int, args: dict) -> MCPCallResponse:
    query = (args.get("query") or args.get("q") or "").strip()
    if not query:
        return _resp({"ok": False, "detail": "query is required"}, True)
    limit = min(int(args.get("limit") or 8), 20)
    from core.database.session import async_session
    from plugins.notes.backend.rag import hybrid_search, ensure_indexed
    try:
        await ensure_indexed(user_id)
        async with async_session() as db:
            results = await hybrid_search(db, user_id, query, top_k=limit)
        return _resp({"ok": True, "query": query, "results": results})
    except Exception as e:
        return _resp({"ok": False, "detail": str(e)}, True)


register_plugin_tool_handler("ask_notes", ask_notes)
register_plugin_tool_handler("search_notes_semantic", search_notes_semantic)
