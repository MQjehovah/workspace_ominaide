import json
from datetime import datetime, timezone
from core.mcp.core import MCPCallResponse, MCPContent


async def get_system_context(user_id: int, args: dict) -> MCPCallResponse:
    """Get current user context: system info, stats, etc."""
    from core.database.session import async_session
    from sqlalchemy import select, func
    from plugins.files.backend.models import File
    from plugins.workspaces.backend.models import Workspace

    async with async_session() as db:
        file_count = (await db.execute(
            select(func.count()).where(File.user_id == user_id, File.status == "active")
        )).scalar() or 0

        ws_count = (await db.execute(
            select(func.count()).where(Workspace.user_id == user_id)
        )).scalar() or 0

    context = {
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_files": file_count,
            "total_workspaces": ws_count,
        },
        "capabilities": [
            "search_files", "list_files", "get_file", "get_file_download_url",
            "list_workspaces", "get_system_context",
        ],
    }
    return MCPCallResponse(content=[MCPContent(text=json.dumps(context, ensure_ascii=False, default=str))])
