import json
from datetime import datetime, timezone
from core.ai.mcp.core import MCPCallResponse, MCPContent


async def get_system_context(user_id: int, args: dict) -> MCPCallResponse:
    """Get current user context: system info, stats, etc."""
    from core.database.session import async_session
    from sqlalchemy import select, func
    from plugins.files.backend.models import File

    async with async_session() as db:
        file_count = (await db.execute(
            select(func.count()).where(File.user_id == user_id, File.status == "active")
        )).scalar() or 0

    context = {
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_files": file_count,
        },
        "capabilities": [
            "search_files", "list_files", "get_file", "get_file_download_url",
            "list_schedule_events", "search_articles", "list_notifications",
            "unified_search", "get_system_context",
        ],
    }
    return MCPCallResponse(content=[MCPContent(text=json.dumps(context, ensure_ascii=False, default=str))])
