"""Mark a DingTalk conversation as read in DingTalk and the local cache."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from core.database.session import async_session
from core.activities.models import UserActivity
from core.logging import get_logger
from plugins.dingtalk.backend import mcp
from plugins.dingtalk.backend.models import DingTalkConversation

log = get_logger(__name__)


def _unwrap(payload, key: str):
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    for _ in range(5):
        if isinstance(data, dict) and key in data:
            return data[key]
        if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
            data = data["data"]
            continue
        if isinstance(data, dict) and isinstance(data.get("result"), (dict, list)):
            data = data["result"]
            continue
        break
    return data if isinstance(data, list) else []


async def _latest_message_id(user_id: int, conversation_id: str) -> str | None:
    try:
        payload = await mcp.call(
            user_id,
            "list_chat_messages",
            {"conversation_id": conversation_id, "order": "desc", "limit": 1},
        )
        for item in _unwrap(payload, "messages"):
            if not isinstance(item, dict):
                continue
            value = item.get("messageId") or item.get("id") or item.get("message_id")
            if value:
                return str(value)
    except Exception as exc:
        log.warning("[dingtalk.read] latest message lookup failed: %s", exc)
    return None


async def mark_conversation_read(
    user_id: int,
    conversation_id: str,
    message_id: str | None = None,
) -> dict:
    remote = False
    if not message_id:
        message_id = await _latest_message_id(user_id, conversation_id)
    if message_id:
        try:
            await mcp.call(
                user_id,
                "mark_read",
                {"conversation_id": conversation_id, "message_id": message_id},
            )
            remote = True
        except Exception as exc:
            log.warning("[dingtalk.read] remote mark read failed: %s", exc)

    async with async_session() as db:
        row = (await db.execute(
            select(DingTalkConversation).where(
                DingTalkConversation.user_id == user_id,
                DingTalkConversation.conversation_id == conversation_id,
            )
        )).scalar_one_or_none()
        if row is not None:
            row.unread_count = 0

        since = datetime.now() - timedelta(days=7)
        activities = list((await db.execute(
            select(UserActivity).where(
                UserActivity.user_id == user_id,
                UserActivity.event_type == "dingtalk.conversation",
                UserActivity.created_at >= since,
            )
        )).scalars().all())
        for activity in activities:
            details = activity.details if isinstance(activity.details, dict) else {}
            if str(details.get("conversation_id") or "") != conversation_id:
                continue
            updated = dict(details)
            updated["unread_count"] = 0
            activity.details = updated
        await db.commit()

    return {"read": True, "remote": remote}
