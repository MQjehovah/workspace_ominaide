"""Stable public API for the DingTalk plugin.

Only this module may be imported by other plugins. The private MCP client and
raw MCP tools stay inside the plugin.
"""

from __future__ import annotations

from sqlalchemy import desc, select

from core.database.session import async_session
from plugins.dingtalk.backend import mcp
from plugins.dingtalk.backend.models import DingTalkConversation, DingTalkMessage
from plugins.dingtalk.backend.service import (
    cancel_login,
    dingtalk_status,
    get_login_session,
    logout,
    session_out,
    start_login,
)

__all__ = [
    "cancel_login",
    "cancel_calendar_event",
    "dingtalk_status",
    "get_login_session",
    "list_conversations",
    "list_messages",
    "logout",
    "session_out",
    "start_login",
    "update_calendar_event",
]


async def update_calendar_event(
    user_id: int,
    external_id: str,
    patch: dict,
) -> dict:
    args = {
        "event_id": external_id,
        "confirmed": True,
        "title": patch.get("title"),
        "start": patch.get("start"),
        "end": patch.get("end"),
        "location": patch.get("location"),
    }
    args = {k: v for k, v in args.items() if v not in (None, "")}
    return await mcp.call(user_id, "update_event", args)


async def cancel_calendar_event(user_id: int, external_id: str) -> dict:
    return await mcp.call(
        user_id,
        "cancel_event",
        {"event_id": external_id, "confirmed": True},
    )


async def list_conversations(user_id: int, limit: int = 50) -> list[dict]:
    async with async_session() as db:
        rows = (await db.execute(
            select(DingTalkConversation)
            .where(DingTalkConversation.user_id == user_id)
            .order_by(desc(DingTalkConversation.last_message_at))
            .limit(max(1, min(limit, 200)))
        )).scalars().all()
    return [
        {
            "conversation_id": row.conversation_id,
            "name": row.name or row.conversation_id,
            "kind": row.kind,
            "last_message_at": row.last_message_at.isoformat() if row.last_message_at else None,
            "unread_count": row.unread_count or 0,
        }
        for row in rows
    ]


async def list_messages(
    user_id: int,
    conversation_id: str,
    *,
    limit: int = 100,
    before_id: int | None = None,
) -> list[dict]:
    async with async_session() as db:
        q = select(DingTalkMessage).where(
            DingTalkMessage.user_id == user_id,
            DingTalkMessage.conversation_id == conversation_id,
        )
        if before_id is not None:
            q = q.where(DingTalkMessage.id < before_id)
        rows = (await db.execute(
            q.order_by(desc(DingTalkMessage.id)).limit(max(1, min(limit, 300)))
        )).scalars().all()
    return [
        {
            "id": row.id,
            "message_id": row.message_id,
            "sender": row.sender,
            "text": row.text,
            "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        }
        for row in reversed(rows)
    ]
