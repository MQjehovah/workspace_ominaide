"""Lightweight DingTalk unread-state refresh for badges and inbox triage."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from core.database.session import async_session
from core.events.bus import record_event
from core.logging import get_logger
from core.mcp_hub.models import McpServer
from plugins.dingtalk.backend import mcp
from plugins.dingtalk.backend.models import DingTalkConversation
from core.activities.models import UserActivity

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


async def sync_unread() -> dict:
    async with async_session() as db:
        user_ids = sorted(set((await db.execute(
            select(McpServer.user_id).where(
                McpServer.owner_plugin == "dingtalk",
                McpServer.enabled == True,  # noqa: E712
            )
        )).scalars().all()))

    stats = {"users": len(user_ids), "unread": 0, "updated": 0, "errors": 0}
    for user_id in user_ids:
        try:
            payload = await mcp.call(user_id, "list_unread", {"count": 100})
            unread: dict[str, str] = {}
            for item in _unwrap(payload, "conversations"):
                if not isinstance(item, dict):
                    continue
                cid = str(
                    item.get("conversationId") or item.get("conversation_id") or ""
                ).strip()
                if cid:
                    unread[cid] = str(item.get("name") or cid)
            stats["unread"] += len(unread)

            since = datetime.now() - timedelta(days=7)
            async with async_session() as db:
                conversations = list((await db.execute(
                    select(DingTalkConversation).where(
                        DingTalkConversation.user_id == user_id,
                    )
                )).scalars().all())
                by_cid = {row.conversation_id: row for row in conversations}
                for row in conversations:
                    row.unread_count = 1 if row.conversation_id in unread else 0
                now = datetime.now()
                for cid, name in unread.items():
                    row = by_cid.get(cid)
                    if row is None:
                        row = DingTalkConversation(
                            user_id=user_id,
                            conversation_id=cid,
                            name=name[:300],
                            unread_count=1,
                            last_message_at=now,
                        )
                        db.add(row)
                        by_cid[cid] = row
                    else:
                        row.name = row.name or name[:300]
                        row.unread_count = 1
                        if row.last_message_at is None:
                            row.last_message_at = now

                rows = list((await db.execute(
                    select(UserActivity)
                    .where(
                        UserActivity.user_id == user_id,
                        UserActivity.event_type == "dingtalk.conversation",
                        UserActivity.created_at >= since,
                    )
                    .order_by(UserActivity.id.desc())
                )).scalars().all())

                seen: set[str] = set()
                for row in rows:
                    details = row.details if isinstance(row.details, dict) else {}
                    cid = str(details.get("conversation_id") or "").strip()
                    if not cid or cid in seen:
                        continue
                    seen.add(cid)
                    value = 1 if cid in unread else 0
                    if (
                        "unread_count" not in details
                        or int(details.get("unread_count") or 0) != value
                    ):
                        updated = dict(details)
                        updated["unread_count"] = value
                        row.details = updated
                        stats["updated"] += 1

                for cid, name in unread.items():
                    if cid in seen:
                        continue
                    await record_event(
                        db,
                        user_id,
                        "dingtalk.conversation",
                        "dingtalk",
                        None,
                        f"钉钉未读 · {name}",
                        {
                            "conversation": name,
                            "conversation_id": cid,
                            "day": datetime.now().strftime("%Y-%m-%d"),
                            "message_count": 0,
                            "content": "",
                            "unread_count": 1,
                        },
                    )
                    stats["updated"] += 1
                await db.commit()
        except Exception as exc:
            log.warning(f"[dingtalk.unread] user {user_id}: {exc}")
            stats["errors"] += 1
    return stats
