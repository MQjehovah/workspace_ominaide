"""Periodic activity insight extraction.

LLM calls happen only in the scheduler job, never in a request handler.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import select

from core.config.settings import settings
from core.database.session import async_session
from core.events.models import UserActivity
from core.logging import get_logger
from core.insights.models import ActivitySuggestion

log = get_logger(__name__)

_SYSTEM = (
    "你是用户的私人助理。根据最近的活动事件，提取用户接下来值得处理的事项。"
    '只输出 JSON：{"items":[{"kind":"todo|event|follow_up|review",'
    '"title":"6-18个字","reason":"一句话原因","confidence":0.0}]}。'
    "最多 5 条，只依据给定数据，不要编造。"
)


async def extract_suggestions() -> dict:
    since = datetime.now() - timedelta(days=2)
    async with async_session() as db:
        events = list((await db.execute(
            select(UserActivity)
            .where(UserActivity.created_at >= since)
            .order_by(UserActivity.id.desc())
            .limit(300)
        )).scalars().all())
        if not events:
            return {"events": 0, "users": 0}
        user_ids = sorted({event.user_id for event in events})
        existing = list((await db.execute(
            select(ActivitySuggestion).where(
                ActivitySuggestion.user_id.in_(user_ids),
                ActivitySuggestion.created_at >= since,
            )
        )).scalars().all())
    processed: dict[int, set[int]] = {}
    for suggestion in existing:
        for event_id in suggestion.source_event_ids or []:
            processed.setdefault(suggestion.user_id, set()).add(int(event_id))

    by_user: dict[int, list[UserActivity]] = {}
    for event in events:
        if event.id in processed.get(event.user_id, set()):
            continue
        by_user.setdefault(event.user_id, []).append(event)

    created = 0
    for user_id, rows in by_user.items():
        rows = rows[:30]
        items = await _extract_with_llm(rows)
        if not items:
            items = _fallback(rows)
        if not items:
            continue
        source_ids = [row.id for row in rows]
        async with async_session() as db:
            for item in items[:5]:
                title = str(item.get("title") or "").strip()
                if not title:
                    continue
                db.add(ActivitySuggestion(
                    user_id=user_id,
                    kind=str(item.get("kind") or "follow_up")[:20],
                    title=title[:200],
                    reason=str(item.get("reason") or "")[:500] or None,
                    confidence=float(item.get("confidence") or 0.5),
                    source_event_ids=source_ids,
                    expires_at=datetime.now() + timedelta(days=7),
                ))
                created += 1
            await db.commit()
    return {"events": len(events), "users": len(by_user), "created": created}


async def _extract_with_llm(rows: list[UserActivity]) -> list[dict] | None:
    if not settings.llm_api_key:
        return None
    from core.cos.service import _llm_json

    payload = [
        {
            "type": row.event_type,
            "summary": row.summary,
            "details": row.details if isinstance(row.details, dict) else {},
        }
        for row in rows
    ]
    result = await _llm_json(
        _SYSTEM,
        json.dumps(payload, ensure_ascii=False)[:12000],
        max_chars=12000,
    )
    items = result.get("items") if isinstance(result, dict) else None
    return items if isinstance(items, list) else None


def _fallback(rows: list[UserActivity]) -> list[dict]:
    items: list[dict] = []
    for row in rows:
        details = row.details if isinstance(row.details, dict) else {}
        if row.event_type == "dingtalk.conversation":
            name = str(details.get("conversation") or "钉钉会话")
            items.append({
                "kind": "follow_up",
                "title": f"跟进{name}"[:18],
                "reason": "钉钉最近会话",
                "confidence": 0.4,
            })
        elif row.event_type.startswith("calendar.external."):
            title = str(details.get("title") or "日程")
            items.append({
                "kind": "event",
                "title": f"准备{title}"[:18],
                "reason": "即将开始的日程",
                "confidence": 0.4,
            })
        if len(items) >= 5:
            break
    return items


async def list_suggestions(user_id: int, limit: int = 20) -> list[dict]:
    async with async_session() as db:
        rows = list((await db.execute(
            select(ActivitySuggestion)
            .where(
                ActivitySuggestion.user_id == user_id,
                ActivitySuggestion.status == "new",
            )
            .order_by(ActivitySuggestion.created_at.desc())
            .limit(max(1, min(limit, 50)))
        )).scalars().all())
    return [
        {
            "id": row.id,
            "kind": row.kind,
            "title": row.title,
            "reason": row.reason,
            "confidence": row.confidence,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


async def set_status(user_id: int, suggestion_id: int, status: str) -> bool:
    async with async_session() as db:
        row = (await db.execute(
            select(ActivitySuggestion).where(
                ActivitySuggestion.id == suggestion_id,
                ActivitySuggestion.user_id == user_id,
            )
        )).scalar_one_or_none()
        if row is None:
            return False
        row.status = status
        await db.commit()
        return True
