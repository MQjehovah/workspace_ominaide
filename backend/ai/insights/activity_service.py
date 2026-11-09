"""Hourly activity analysis and actionable suggestions.

The LLM runs only in the scheduled background job. Request handlers read the
latest suggestions from the database.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import select

from core.config.settings import settings
from ai.context import build_context
from ai.cognition.proposals import create_proposal, expire_old
from core.database.session import async_session
from activities.models import UserActivity
from core.logging import get_logger

log = get_logger(__name__)

_SYSTEM = (
    "你是用户的私人助理。根据用户最近的活动、未来 48 小时日程、待办、未读邮件、"
    "钉钉会话和资讯，预判接下来值得处理的事，给出最多 5 条建议。"
    '只输出 JSON：{"suggestions":[{"kind":"todo|prepare|reply|schedule|review",'
    '"title":"6-18个字","reason":"一句话原因","confidence":0.0,'
    '"action":null}]}。'
    "action 只能为 null 或 {\"type\":\"create_todo\",\"payload\":{\"title\":\"...\","
    "\"description\":\"...\",\"priority\":1,\"due_date\":\"ISO时间或null\"}}。"
    "没有明确截止时间时不要编造时间。只依据给定数据，不要编造。"
)

_ALLOWED_ACTIONS = {"create_todo"}


def _compact(value, limit: int = 400) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _prompt_payload(context: dict, activities: list[UserActivity]) -> dict:
    return {
        "now": context["now"],
        "events": [
            {
                "time": item.get("time"),
                "title": item.get("title"),
                "summary": _compact(item.get("summary"), 200),
            }
            for item in context.get("events", [])
        ],
        "todos": [
            {
                "title": item.get("title"),
                "due": (item.get("meta") or {}).get("due"),
                "priority": item.get("priority"),
            }
            for item in context.get("todos", [])
        ],
        "unread_mail": [
            {
                "from": item.get("from"),
                "subject": item.get("title"),
                "summary": _compact(item.get("summary"), 200),
            }
            for item in context.get("unread_mail", [])
        ],
        "dingtalk": [
            {"conversation": item.get("title"), "text": _compact(item.get("summary"), 250)}
            for item in context.get("dingtalk", [])
        ],
        "news": [
            {"title": item.get("title"), "summary": _compact(item.get("summary"), 150)}
            for item in context.get("news", [])
        ],
        "recent_notes": context.get("recent_notes", []),
        "recent_files": context.get("recent_files", []),
        "recent_projects": context.get("recent_projects", []),
        "memory": context.get("memory", []),
        "activities": [
            {
                "type": row.event_type,
                "summary": row.summary,
                "details": {
                    str(key): _compact(value, 300)
                    for key, value in (row.details or {}).items()
                    if isinstance(value, (str, int, float, bool))
                } if isinstance(row.details, dict) else {},
            }
            for row in activities[:60]
        ],
    }


async def _extract_with_llm(context: dict, activities: list[UserActivity]) -> list[dict] | None:
    if not settings.llm_api_key:
        return None
    from ai.llm import llm_json

    payload = _prompt_payload(context, activities)
    result = await llm_json(
        _SYSTEM,
        json.dumps(payload, ensure_ascii=False, default=str)[:12000],
        max_chars=12000,
    )
    items = result.get("suggestions") if isinstance(result, dict) else None
    return items if isinstance(items, list) else None


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _fallback(context: dict, activities: list[UserActivity]) -> list[dict]:
    items: list[dict] = []
    now = datetime.now()
    overdue = [
        todo for todo in context.get("todos", [])
        if _parse_dt((todo.get("meta") or {}).get("due"))
        and _parse_dt((todo.get("meta") or {}).get("due")) < now
    ]
    if overdue:
        title = str(overdue[0].get("title") or "逾期事项")
        items.append({
            "kind": "todo",
            "title": f"处理逾期：{title}"[:18],
            "reason": "待办已经超过截止时间",
            "confidence": 0.7,
        })
    events = context.get("events", [])
    if events:
        event = events[0]
        items.append({
            "kind": "prepare",
            "title": f"准备{event.get('title') or '日程'}"[:18],
            "reason": "接下来 48 小时内有日程",
            "confidence": 0.55,
        })
    mail = context.get("unread_mail", [])
    if mail:
        sender = str(mail[0].get("from") or "未读邮件")
        items.append({
            "kind": "reply",
            "title": f"回复{sender}"[:18],
            "reason": "有未读邮件待处理",
            "confidence": 0.5,
        })
    if context.get("dingtalk"):
        name = str(context["dingtalk"][0].get("title") or "钉钉会话")
        items.append({
            "kind": "reply",
            "title": f"跟进{name}"[:18],
            "reason": "钉钉最近有会话活动",
            "confidence": 0.45,
        })
    if not items:
        for activity in activities:
            if activity.event_type == "dingtalk.conversation":
                details = activity.details if isinstance(activity.details, dict) else {}
                name = str(details.get("conversation") or "钉钉会话")
                items.append({
                    "kind": "follow_up",
                    "title": f"跟进{name}"[:18],
                    "reason": "钉钉最近会话",
                    "confidence": 0.4,
                })
                break
    return items[:5]


def _sanitize_action(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    action_type = str(value.get("type") or "").strip()
    if action_type not in _ALLOWED_ACTIONS:
        return None
    payload = value.get("payload")
    if not isinstance(payload, dict):
        return None
    title = str(payload.get("title") or "").strip()
    if not title:
        return None
    clean = {"type": action_type, "payload": {"title": title[:200]}}
    if payload.get("description"):
        clean["payload"]["description"] = str(payload["description"])[:500]
    try:
        clean["payload"]["priority"] = max(0, min(int(payload.get("priority") or 1), 3))
    except (TypeError, ValueError):
        clean["payload"]["priority"] = 1
    if payload.get("due_date"):
        clean["payload"]["due_date"] = str(payload["due_date"])
    return clean


async def _all_user_ids() -> list[int]:
    from core.auth.domain.models import User

    async with async_session() as db:
        return list((await db.execute(select(User.id).order_by(User.id))).scalars().all())


async def analyze_user(user_id: int) -> dict:
    context = await build_context(user_id, horizon_hours=48)
    since = datetime.now() - timedelta(days=2)
    async with async_session() as db:
        activities = list((await db.execute(
            select(UserActivity)
            .where(
                UserActivity.user_id == user_id,
                UserActivity.created_at >= since,
            )
            .order_by(UserActivity.id.desc())
            .limit(100)
        )).scalars().all())

    items = await _extract_with_llm(context, activities)
    if not items:
        items = _fallback(context, activities)

    source_ids = [row.id for row in activities[:60]]
    await expire_old(user_id)
    created = 0
    for item in items[:5]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        action = _sanitize_action(item.get("action"))
        actions = []
        if action:
            kind = str(action.get("type") or "none")
            actions.append({
                "key": kind,
                "label": "",
                "kind": kind,
                "payload": action.get("payload") or {},
            })
        await create_proposal(
            user_id,
            kind=str(item.get("kind") or "follow_up")[:24],
            title=title,
            reason=str(item.get("reason") or "")[:500] or None,
            evidence={"source_event_ids": source_ids},
            confidence=float(item.get("confidence") or 0.5),
            actions=actions,
            channel="now",
            dedupe_key=f"activity:{user_id}:{title[:120]}",
            expires_at=datetime.now() + timedelta(days=7),
        )
        created += 1
    return {"user_id": user_id, "created": created, "activities": len(activities)}


async def enqueue_activity_analyses() -> dict:
    bucket = datetime.now().strftime("%Y%m%d%H")
    user_ids = await _all_user_ids()
    from core.jobs.service import enqueue

    for user_id in user_ids:
        await enqueue(
            "core.activity_analysis.user",
            {"user_id": int(user_id)},
            idempotency_key=f"analysis:{user_id}:{bucket}",
        )
    return {"users": len(user_ids), "bucket": bucket}
