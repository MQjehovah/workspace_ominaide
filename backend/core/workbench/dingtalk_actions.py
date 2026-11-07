"""Read-only DingTalk action suggestions.

The product deliberately does not mirror DingTalk chat or send replies. It
reads unread conversations/calendar/todos and turns them into actionable
suggestions that the user can accept as local todos, events or notes.
"""

from __future__ import annotations

import json
import time
from datetime import datetime

from core.cos import collectors
from core.cos.service import _llm_json

_TTL = 600.0
_CACHE: dict[int, tuple[float, dict]] = {}

_SYSTEM = (
    "你是用户的私人助理。根据钉钉未读会话、即将开始的日程和待办，"
    "判断用户接下来需要处理什么。只输出 JSON："
    '{"items":[{"title":"短动作","reason":"一句话原因","kind":"todo|meeting|follow_up|review","conversation":"来源会话"}]}。'
    "最多 5 条，每条动作 6-18 个中文字符；只依据给定数据，不要编造。"
)


def _short(value, limit: int = 18) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _fallback(dingtalk: list[dict], events: list[dict], todos: list[dict]) -> list[dict]:
    items: list[dict] = []
    for row in dingtalk[:4]:
        summary = _short(row.get("summary") or row.get("title"), 14)
        title = f"跟进：{summary}" if summary else f"处理{row.get('title', '钉钉消息')}"
        items.append(
            {
                "title": title,
                "reason": "钉钉未读会话",
                "kind": "follow_up",
                "conversation": row.get("title") or "",
            }
        )
    for row in events[:2]:
        at = row.get("time")
        title = _short(row.get("title"), 12)
        if title:
            items.append(
                {
                    "title": f"准备{title}",
                    "reason": f"日程 {str(at or '')[:16]}",
                    "kind": "meeting",
                    "conversation": "",
                }
            )
    for row in todos[:2]:
        title = _short(row.get("title"), 12)
        if title:
            items.append(
                {
                    "title": f"推进：{title}",
                    "reason": "待办提醒",
                    "kind": "todo",
                    "conversation": "",
                }
            )
    result: list[dict] = []
    seen: set[str] = set()
    for item in items:
        key = item["title"]
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= 5:
            break
    return result


async def dingtalk_actions(user_id: int, *, refresh: bool = False) -> dict:
    cached = _CACHE.get(user_id)
    if cached and not refresh and time.monotonic() - cached[0] < _TTL:
        return cached[1]
    if not refresh:
        from core.cache import get_json

        redis_cached = await get_json(f"workbench:dingtalk-actions:{user_id}")
        if isinstance(redis_cached, dict):
            _CACHE[user_id] = (time.monotonic(), redis_cached)
            return redis_cached

    now = datetime.now()
    dingtalk, status = await collectors.dingtalk_items(user_id, limit=10)
    events = await collectors.schedule_items(
        user_id,
        start=now,
        end=now.replace(hour=23, minute=59, second=59),
        limit=5,
    )
    todos = await collectors.todo_items(user_id, limit=5)

    items = _fallback(dingtalk, events, todos)
    source = "fallback"
    context = {
        "dingtalk": [
            {"conversation": row.get("title"), "text": row.get("summary")}
            for row in dingtalk
        ],
        "events": [
            {"time": row.get("time"), "title": row.get("title")} for row in events
        ],
        "todos": [{"title": row.get("title")} for row in todos],
    }
    try:
        from core.bots.registry import get_active_bot

        bot = await get_active_bot(user_id)
        enriched = await _llm_json(
            _SYSTEM,
            json.dumps(context, ensure_ascii=False),
            bot=bot,
        )
        raw = enriched.get("items") if isinstance(enriched, dict) else None
        if isinstance(raw, list):
            clean = []
            for row in raw:
                if not isinstance(row, dict):
                    continue
                title = _short(row.get("title"), 24)
                if not title:
                    continue
                clean.append(
                    {
                        "title": title,
                        "reason": _short(row.get("reason"), 60),
                        "kind": str(row.get("kind") or "follow_up"),
                        "conversation": str(row.get("conversation") or ""),
                    }
                )
            if clean:
                items = (clean + items)[:5]
                source = "llm"
    except Exception as exc:
        print(f"[dingtalk-actions] llm error: {exc}")

    payload = {
        "items": items,
        "source": source,
        "dingtalk_status": status,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    _CACHE[user_id] = (time.monotonic(), payload)
    from core.cache import set_json

    await set_json(
        f"workbench:dingtalk-actions:{user_id}",
        payload,
        int(_TTL),
    )
    return payload
