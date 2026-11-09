"""Let a Bot actively push a notification to its user.

Event-triggered routines are silent by default: the model decides whether the
event is worth interrupting the user and calls this tool only when it is.
"""

from ai.mcp.core import MCPCallResponse, MCPContent, MCPTool


def _ok(text: str) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=text)])


def _err(text: str) -> MCPCallResponse:
    return MCPCallResponse(isError=True, content=[MCPContent(text=text)])


async def send_notification(user_id: int, args: dict) -> MCPCallResponse:
    title = str(args.get("title") or "").strip()[:200]
    body = str(args.get("body") or "").strip()[:2000]
    link = str(args.get("link") or "/notifications").strip() or "/notifications"
    if not title and not body:
        return _err("title or body is required")

    from ai.bots.context import get_current_run_id
    from core.database.session import async_session
    from plugins.notifications.backend.router import notify_user
    from plugins.notifications.backend.service import create_notification

    run_id = get_current_run_id()
    try:
        async with async_session() as db:
            note = await create_notification(
                db, user_id,
                title or "提醒",
                body,
                "bot_run",
                link,
                dedupe_key=f"bot-notify:{run_id}:{title[:60]}" if run_id else None,
            )
            await db.commit()
            note_id = note.id
        try:
            await notify_user(user_id, {
                "type": "new_notification",
                "id": note_id,
                "title": title or "提醒",
                "body": body,
                "link": link,
            })
        except Exception:
            pass
        return _ok(f"已发送通知 #{note_id}")
    except Exception as e:  # noqa: BLE001
        return _err(f"通知发送失败: {e}")


TOOLS = [
    (
        MCPTool(
            name="send_notification",
            description=(
                "给用户发送一条通知。事件触发器默认不会自动通知，"
                "只有确实需要打断用户时才调用。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "通知标题，建议 20 字以内"},
                    "body": {"type": "string", "description": "通知正文，2-4 句中文"},
                    "link": {"type": "string", "description": "点击后跳转的站内路径，如 /mail"},
                },
                "required": ["title", "body"],
            },
        ),
        send_notification,
    )
]
