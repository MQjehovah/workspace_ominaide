import json
from domains.mcp.core import MCPCallResponse, MCPContent
from domains.mcp.registry import tool_registry, MCPTool
from domains.workspace.service import get_workspaces


async def list_workspaces_tool(user_id: int, args: dict) -> MCPCallResponse:
    """List all workspaces for the current user."""
    from core.database.session import async_session
    async with async_session() as db:
        workspaces = await get_workspaces(db, user_id)

    results = [
        {
            "id": w.id,
            "name": w.name,
            "description": w.description,
            "sync_enabled": w.sync_enabled,
            "created_at": w.created_at.isoformat() if w.created_at else None,
        }
        for w in workspaces
    ]
    return MCPCallResponse(content=[MCPContent(text=json.dumps(results, ensure_ascii=False, default=str))])
