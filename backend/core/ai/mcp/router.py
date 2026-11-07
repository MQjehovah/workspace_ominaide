
from core.logging import get_logger
log = get_logger(__name__)
from fastapi import APIRouter, Depends
import time

from core.auth.dependencies import get_current_user
from core.ai.mcp.registry import tool_registry
from core.ai.mcp.core import MCPCallRequest

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


@router.get("/tools")
async def list_tools(user: dict = Depends(get_current_user)):
    """MCP: List all tools available to the current user with their schemas."""
    tools = tool_registry.get_tools(user_id=user["id"])
    return {"tools": [t.model_dump() for t in tools]}


@router.post("/call")
async def call_tool(
    req: MCPCallRequest,
    user: dict = Depends(get_current_user),
):
    """MCP: Call a tool with arguments and get results."""
    started = time.perf_counter()
    result = await tool_registry.call(user["id"], req)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if hasattr(result, "model_dump"):
        payload = result.model_dump()
    else:
        # safety fallback
        from core.ai.mcp.registry import _to_response
        payload = _to_response(result).model_dump()

    # Activity middleware skips /api/mcp/call, so record the tool name here.
    try:
        from core.database.session import async_session
        from core.events.bus import record_event
        from core.events.preview import preview_arguments

        is_error = bool(payload.get("isError"))
        keys = sorted(str(k) for k in (req.arguments or {}).keys())[:20]
        status = "失败" if is_error else "成功"
        async with async_session() as db:
            await record_event(
                db, user["id"], "mcp.tool.called", "mcp", None,
                f"{req.name} · {status} · {elapsed_ms}ms",
                {
                    "tool": req.name,
                    "argument_keys": keys,
                    "arguments_preview": preview_arguments(req.arguments),
                    "is_error": is_error,
                    "duration_ms": elapsed_ms,
                },
            )
            await db.commit()
    except Exception as e:
        log.warning(f"[mcp] activity record failed: {e}")

    return payload
