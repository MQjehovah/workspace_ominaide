"""Personal info agent tools: let the voice/chat agent read the user's
unread notifications and latest RSS headlines aloud ("帮我读一下通知/新闻").
"""
from core.ai.mcp.core import MCPTool, MCPCallResponse, MCPContent
from core.config.settings import settings


def _ok(text: str) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=text)])


async def get_unread_notifications(user_id: int, args: dict) -> MCPCallResponse:
    limit = min(int(args.get("limit") or 8), 20)
    try:
        from sqlalchemy import select
        from core.database.session import async_session
        from plugins.notifications.backend.models import Notification

        async with async_session() as db:
            r = await db.execute(
                select(Notification)
                .where(Notification.user_id == user_id, Notification.read == False)  # noqa: E712
                .order_by(Notification.created_at.desc())
                .limit(limit)
            )
            items = list(r.scalars().all())
    except Exception as e:
        return MCPCallResponse(isError=True, content=[MCPContent(text=f"查询失败: {e}")])

    if not items:
        return _ok("没有未读通知。")
    lines = [f"共 {len(items)} 条未读："]
    for i, n in enumerate(items, 1):
        body = f"：{(n.body or '').strip()[:60]}" if n.body else ""
        lines.append(f"{i}. {n.title}{body}")
    return _ok("\n".join(lines))


async def get_latest_news(user_id: int, args: dict) -> MCPCallResponse:
    limit = min(int(args.get("limit") or 6), 15)
    try:
        from core.database.session import async_session
        from plugins.rss.backend import service as rss_service

        async with async_session() as db:
            items, _total = await rss_service.list_entries(
                db, user_id, None, False, False, 1, limit)
    except Exception as e:
        return MCPCallResponse(isError=True, content=[MCPContent(text=f"查询失败: {e}")])

    if not items:
        return _ok("RSS 还没有抓取到任何文章。")
    lines = ["最新资讯："]
    for i, e in enumerate(items, 1):
        lines.append(f"{i}. {e.title}")
    return _ok("\n".join(lines))


TOOLS = [
    (
        MCPTool(
            name="get_latest_news",
            description="读取用户 RSS 订阅的最新文章标题。用户问\"有什么新闻/资讯\"时调用。",
            inputSchema={
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "条数，默认 6"}},
            },
        ),
        get_latest_news,
    ),
]
