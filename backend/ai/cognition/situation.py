"""Read-only situation snapshot for chat, proposals and goals."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select

from ai.cognition.goals import list_goals
from ai.cognition.proposals import list_proposals
from ai.context import build_context
from activities.models import UserActivity
from core.cache import delete as cache_delete
from core.cache import get_json, set_json
from core.database.session import async_session
from core.wschannel.hub import host_channel

CACHE_TTL = 60


def _key(user_id: int) -> str:
    return f"cognition:situation:{user_id}"


async def invalidate(user_id: int) -> None:
    await cache_delete(_key(user_id))


async def _recent_activities(user_id: int, limit: int = 20) -> list[dict]:
    async with async_session() as db:
        rows = list((await db.execute(
            select(UserActivity)
            .where(UserActivity.user_id == user_id)
            .order_by(UserActivity.created_at.desc())
            .limit(limit)
        )).scalars().all())
    return [
        {
            "id": row.id,
            "event_type": row.event_type,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "summary": row.summary,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


async def _unread_notifications(user_id: int) -> int:
    from plugins.notifications.backend.models import Notification

    async with async_session() as db:
        return int((await db.execute(
            select(func.count()).select_from(Notification).where(
                Notification.user_id == user_id,
                Notification.read == False,  # noqa: E712
            )
        )).scalar_one() or 0)


def _signals(context: dict, proposals: list[dict]) -> list[dict]:
    now = datetime.now()
    signals: list[dict] = []
    for event in context.get("events", [])[:5]:
        raw = event.get("time")
        if not raw:
            continue
        try:
            start = datetime.fromisoformat(str(raw))
        except ValueError:
            continue
        if start.tzinfo is not None:
            start = start.astimezone().replace(tzinfo=None)
        if now <= start <= now + timedelta(hours=2):
            signals.append({
                "type": "meeting_soon",
                "source": "schedule",
                "title": event.get("title"),
                "at": raw,
                "confidence": 0.95,
                "actionable": True,
            })
    overdue = [
        todo for todo in context.get("todos", [])
        if (todo.get("meta") or {}).get("due")
        and str(todo["meta"]["due"]) < now.isoformat()
    ]
    if overdue:
        signals.append({
            "type": "overdue_todos",
            "source": "todo",
            "count": len(overdue),
            "confidence": 1.0,
            "actionable": True,
        })
    unread = context.get("unread_mail") or []
    if unread:
        signals.append({
            "type": "unread_mail",
            "source": "mail",
            "count": len(unread),
            "confidence": 1.0,
            "actionable": True,
        })
    if proposals:
        signals.append({
            "type": "open_proposals",
            "source": "proposal",
            "count": len(proposals),
            "confidence": 1.0,
            "actionable": True,
        })
    return signals


async def get_situation(user_id: int, *, force: bool = False) -> dict:
    key = _key(user_id)
    if not force:
        cached = await get_json(key)
        if isinstance(cached, dict):
            return cached

    context = await build_context(user_id)
    proposals = await list_proposals(user_id, status="open", limit=5)
    goals = await list_goals(user_id, status="all", limit=20)
    machines = host_channel.machine_ids(user_id)
    snapshot = {
        "user_id": user_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "presence": {
            "online": bool(machines),
            "machines": [
                {"machine_id": mid, "name": host_channel.machine_name(mid)}
                for mid in machines
            ],
        },
        "calendar": context.get("events", []),
        "todos": context.get("todos", []),
        "inbox": {
            "mail_unread": len(context.get("unread_mail") or []),
            "dingtalk_unread": len(context.get("dingtalk") or []),
            "notifications": await _unread_notifications(user_id),
            "recent_mail": (context.get("unread_mail") or [])[:10],
        },
        "recent": {
            "files": context.get("recent_files", []),
            "notes": context.get("recent_notes", []),
            "projects": context.get("recent_projects", []),
            "activities": await _recent_activities(user_id),
        },
        "memory": context.get("memory", []),
        "proposals": proposals,
        "goals": goals,
        "signals": _signals(context, proposals),
    }
    from ai.cognition.situation_entities import build_situation_entities

    snapshot["entities"] = await build_situation_entities(user_id, snapshot)
    await set_json(key, snapshot, ttl_seconds=CACHE_TTL)
    return snapshot


async def situation_prompt(user_id: int) -> str:
    """Compact situation text for chat system prompts."""
    try:
        snapshot = await get_situation(user_id)
    except Exception:
        return ""
    lines = []
    events = snapshot.get("calendar") or []
    if events:
        lines.append("接下来日程：" + "；".join(
            f"{str(e.get('time') or '')[11:16]} {e.get('title')}" for e in events[:3]
        ))
    todos = snapshot.get("todos") or []
    if todos:
        lines.append("待办：" + "；".join(str(t.get("title")) for t in todos[:3]))
    inbox = snapshot.get("inbox") or {}
    if inbox.get("mail_unread") or inbox.get("dingtalk_unread"):
        lines.append(
            f"未读：邮件 {inbox.get('mail_unread', 0)}，钉钉 {inbox.get('dingtalk_unread', 0)}"
        )
    proposals = snapshot.get("proposals") or []
    if proposals:
        lines.append("待处理提案：" + "；".join(str(p.get("title")) for p in proposals[:3]))
    return "\n".join(lines)
