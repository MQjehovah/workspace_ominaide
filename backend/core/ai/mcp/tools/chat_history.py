"""Read recent chat conversations for the daily memory agent."""

import json
from datetime import datetime, timedelta

from sqlalchemy import desc, select

from core.ai.mcp.core import MCPCallResponse, MCPContent, MCPTool


def _ok(text: str) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=text)])


async def list_recent_chats(user_id: int, args: dict) -> MCPCallResponse:
    from core.database.session import async_session
    from plugins.chat.backend.models import ChatMessage, ChatSession

    hours = max(1, min(int(args.get("hours") or 24), 72))
    limit = max(1, min(int(args.get("limit") or 50), 100))
    max_chars = max(2000, min(int(args.get("max_chars") or 20000), 60000))
    since = datetime.utcnow() - timedelta(hours=hours)

    async with async_session() as db:
        sessions = list((await db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id, ChatSession.updated_at >= since)
            .order_by(desc(ChatSession.updated_at))
            .limit(limit)
        )).scalars().all())
        titles = {s.session_id: s.title for s in sessions}

        rows = list((await db.execute(
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id, ChatMessage.created_at >= since)
            .order_by(ChatMessage.id)
        )).scalars().all())

    grouped: dict[str, list] = {}
    for msg in rows:
        grouped.setdefault(msg.session_id, []).append(msg)

    # Include sessions that only exist in messages but have no ChatSession row.
    for session_id in grouped:
        titles.setdefault(session_id, None)

    output = []
    used = 0
    for session_id, messages in list(grouped.items())[:limit]:
        items = []
        for msg in messages[-40:]:
            content = (msg.content or "").strip()
            if not content:
                continue
            remaining = max_chars - used
            if remaining <= 0:
                break
            content = content[:min(600, remaining)]
            used += len(content)
            items.append({
                "role": msg.role,
                "content": content,
                "time": str(msg.created_at or ""),
            })
        if items:
            output.append({
                "session_id": session_id,
                "title": titles.get(session_id) or "",
                "messages": items,
            })
        if used >= max_chars:
            break

    return _ok(json.dumps({
        "hours": hours,
        "sessions": output,
        "truncated": used >= max_chars,
    }, ensure_ascii=False))


TOOLS = [
    (
        MCPTool(
            name="list_recent_chats",
            description=(
                "读取最近的聊天会话和消息，用于整理当天对话、提取长期记忆。"
                "返回所有会话，内容按总字符数截断。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "hours": {"type": "integer", "description": "回看小时数，默认 24"},
                    "limit": {"type": "integer", "description": "最多会话数，默认 50"},
                    "max_chars": {"type": "integer", "description": "总字符上限，默认 20000"},
                },
            },
        ),
        list_recent_chats,
    )
]
