"""Sync DingTalk conversations into the plugin cache and activity stream."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from sqlalchemy import select

from core.database.session import async_session
from core.events.bus import record_event
from core.activities.models import UserActivity
from core.logging import get_logger
from core.mcp_hub.models import McpServer
from core.timeutil import naive_local
from plugins.dingtalk.backend import mcp
from plugins.dingtalk.backend.models import DingTalkConversation, DingTalkMessage

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


def _dt(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000.0
        try:
            return datetime.fromtimestamp(number)
        except (OSError, ValueError):
            return None
    try:
        return naive_local(value)
    except Exception:
        return None


async def _upsert_conversation(
    user_id: int, conv: dict, unread_count: int | None = None
) -> str | None:
    conversation_id = str(conv.get("conversationId") or conv.get("conversation_id") or "").strip()
    if not conversation_id:
        return None
    name = str(conv.get("name") or conv.get("title") or conversation_id)
    kind = str(conv.get("type") or conv.get("conversationType") or "")
    last_at = _dt(conv.get("lastMessageTime") or conv.get("last_message_time") or conv.get("updateTime"))
    unread = (
        int(unread_count)
        if unread_count is not None
        else int(conv.get("unreadCount") or conv.get("unread_count") or 0)
    )
    async with async_session() as db:
        row = (await db.execute(
            select(DingTalkConversation).where(
                DingTalkConversation.user_id == user_id,
                DingTalkConversation.conversation_id == conversation_id,
            )
        )).scalar_one_or_none()
        if row is None:
            row = DingTalkConversation(
                user_id=user_id,
                conversation_id=conversation_id,
            )
            db.add(row)
        row.name = name[:300]
        row.kind = kind[:30] or None
        if last_at is not None:
            row.last_message_at = last_at
        row.unread_count = unread
        await db.commit()
    return conversation_id


async def _upsert_messages(user_id: int, conversation_id: str, messages: list[dict]) -> list[str]:
    lines: list[str] = []
    async with async_session() as db:
        for idx, msg in enumerate(messages):
            text = str(msg.get("text") or msg.get("content") or "").strip()
            if not text:
                continue
            sender = str(msg.get("sender") or msg.get("senderName") or "").strip()
            sent_at = _dt(msg.get("createTime") or msg.get("sentAt") or msg.get("time"))
            message_id = str(msg.get("id") or msg.get("messageId") or f"{sent_at}:{idx}")
            row = (await db.execute(
                select(DingTalkMessage).where(
                    DingTalkMessage.user_id == user_id,
                    DingTalkMessage.conversation_id == conversation_id,
                    DingTalkMessage.message_id == message_id,
                )
            )).scalar_one_or_none()
            if row is None:
                row = DingTalkMessage(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    message_id=message_id,
                )
                db.add(row)
            row.sender = sender[:200] or None
            row.text = text[:8000]
            row.sent_at = sent_at
            row.raw = msg
            lines.append(f"{sender}: {text}" if sender else text)
        await db.commit()
    return lines


async def _publish_activity(
    user_id: int,
    conversation_id: str,
    name: str,
    lines: list[str],
    unread_count: int = 0,
) -> None:
    if not lines:
        return
    day_key = datetime.now().strftime("%Y-%m-%d")
    content = "\n".join(lines)[:8000]
    content_hash = hashlib.sha1(content.encode("utf-8")).hexdigest()
    async with async_session() as db:
        recent = (await db.execute(
            select(UserActivity).where(
                UserActivity.user_id == user_id,
                UserActivity.event_type == "dingtalk.conversation",
                UserActivity.created_at >= datetime.now() - timedelta(days=7),
            )
        )).scalars().all()
        # Publish a new event only when the synced content actually changed.
        # Keep the read/unread count fresh even when the text is unchanged.
        for row in recent:
            details = row.details if isinstance(row.details, dict) else {}
            if str(details.get("conversation_id") or "") != conversation_id:
                continue
            if str(details.get("content_hash") or "") == content_hash:
                if (
                    "unread_count" not in details
                    or int(details.get("unread_count") or 0) != int(unread_count)
                ):
                    updated = dict(details)
                    updated["unread_count"] = int(unread_count)
                    row.details = updated
                    await db.commit()
                return
        await record_event(
            db,
            user_id,
            "dingtalk.conversation",
            "dingtalk",
            None,
            f"钉钉会话 · {name}",
            {
                "conversation": name,
                "conversation_id": conversation_id,
                "day": day_key,
                "message_count": len(lines),
                "content": content,
                "content_hash": content_hash,
                "unread_count": int(unread_count),
            },
        )
        await db.commit()


async def sync_chat() -> dict:
    hours = 24
    max_messages = 200
    now = datetime.now().astimezone().replace(microsecond=0)
    start = (now - timedelta(hours=max(1, hours))).isoformat()
    end = now.isoformat()

    async with async_session() as db:
        user_ids = sorted(set((await db.execute(
            select(McpServer.user_id).where(
                McpServer.owner_plugin == "dingtalk",
                McpServer.enabled == True,  # noqa: E712
            )
        )).scalars().all()))

    stats = {"users": len(user_ids), "conversations": 0, "messages": 0, "errors": 0}
    for user_id in user_ids:
        try:
            unread_ids: set[str] = set()
            try:
                unread_payload = await mcp.call(
                    user_id, "list_unread", {"count": 100}
                )
                for item in _unwrap(unread_payload, "conversations"):
                    if isinstance(item, dict):
                        cid = str(
                            item.get("conversationId")
                            or item.get("conversation_id")
                            or ""
                        ).strip()
                        if cid:
                            unread_ids.add(cid)
            except Exception as exc:
                log.warning(f"[dingtalk.sync] unread list {user_id}: {exc}")

            payload = await mcp.call(user_id, "recent_conversations", {"start": start})
            conversations = _unwrap(payload, "conversations")
            if not isinstance(conversations, list):
                continue
            for conv in conversations[:50]:
                if not isinstance(conv, dict):
                    continue
                conv_id = str(
                    conv.get("conversationId") or conv.get("conversation_id") or ""
                ).strip()
                conversation_id = await _upsert_conversation(
                    user_id, conv,
                    unread_count=1 if conv_id in unread_ids else 0,
                )
                if not conversation_id:
                    continue
                try:
                    msg_payload = await mcp.call(
                        user_id,
                        "list_chat_messages",
                        {
                            "conversation_id": conversation_id,
                            "start": start,
                            "end": end,
                            # Fetch newest first so the cap keeps recent
                            # messages, then restore chronological order.
                            "order": "desc",
                            "limit": max(1, min(max_messages, 500)),
                        },
                    )
                except Exception as exc:
                    log.warning(f"[dingtalk.sync] messages {conversation_id}: {exc}")
                    stats["errors"] += 1
                    continue
                messages = _unwrap(msg_payload, "messages")
                if isinstance(messages, list):
                    messages = list(reversed(messages))
                else:
                    messages = []
                lines = await _upsert_messages(
                    user_id, conversation_id, messages
                )
                if lines:
                    stats["messages"] += len(lines)
                    name = str(conv.get("name") or conv.get("title") or conversation_id)
                    unread = 1 if conversation_id in unread_ids else 0
                    await _publish_activity(
                        user_id, conversation_id, name, lines, unread_count=unread,
                    )
                stats["conversations"] += 1
        except Exception as exc:
            log.warning(f"[dingtalk.sync] user {user_id}: {exc}")
            stats["errors"] += 1
    return stats
