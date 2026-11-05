"""Daily insight pipeline.

Every day is analysed exactly once from *that day's* activities and chat
messages. Long-term understanding is built by reading these daily rows, never
by rescanning a 30-day raw window.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from core.config.settings import settings

MAX_ACTIVITIES = 80
MAX_CHAT_PER_SESSION = 20
MAX_CHAT_MESSAGE_CHARS = 500
MAX_DIGEST_CHARS = 6000


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min)
    return start, start + timedelta(days=1)


def _detail_snippet(details: dict | None) -> str:
    if not details:
        return ""
    try:
        text = json.dumps(details, ensure_ascii=False)
    except Exception:
        return ""
    return text[:200]


async def collect_day_data(user_id: int, day: date) -> dict:
    """Collect and aggregate one user's data for one local calendar day.

    Only rows belonging to ``user_id`` and falling inside the day are read.
    """
    from core.database.session import async_session
    from core.events.models import UserActivity
    from plugins.chat.backend.models import ChatMessage
    from plugins.schedule.backend.models import Event
    from plugins.todo.backend.models import PluginTodoItem

    start, end = _day_bounds(day)

    async with async_session() as db:
        activities = list((await db.execute(
            select(UserActivity).where(
                UserActivity.user_id == user_id,
                UserActivity.created_at >= start,
                UserActivity.created_at < end,
                ~UserActivity.event_type.like("device.%"),
            ).order_by(UserActivity.created_at).limit(500)
        )).scalars().all())

        messages = list((await db.execute(
            select(ChatMessage).where(
                ChatMessage.user_id == user_id,
                ChatMessage.created_at >= start,
                ChatMessage.created_at < end,
            ).order_by(ChatMessage.id).limit(1000)
        )).scalars().all())

        todos_done = list((await db.execute(
            select(PluginTodoItem).where(
                PluginTodoItem.user_id == user_id,
                PluginTodoItem.status == "done",
                PluginTodoItem.updated_at >= start,
                PluginTodoItem.updated_at < end,
            ).order_by(PluginTodoItem.updated_at)
        )).scalars().all())

        schedule = list((await db.execute(
            select(Event).where(
                Event.user_id == user_id,
                Event.start_time >= start,
                Event.start_time < end,
            ).order_by(Event.start_time)
        )).scalars().all())

    event_types: dict[str, int] = {}
    app_minutes: dict[str, int] = {}
    activity_lines: list[str] = []
    for e in activities:
        event_types[e.event_type] = event_types.get(e.event_type, 0) + 1
        details = e.details or {}
        app = details.get("app")
        if app:
            try:
                app_minutes[str(app)] = app_minutes.get(str(app), 0) + int(details.get("minutes") or 0)
            except (TypeError, ValueError):
                pass
        if len(activity_lines) < MAX_ACTIVITIES:
            stamp = e.created_at.strftime("%H:%M") if e.created_at else ""
            activity_lines.append(
                f"[{stamp}] {e.event_type}: {e.summary or ''}{(' ' + _detail_snippet(details)) if details else ''}".strip()
            )

    sessions: dict[str, dict] = {}
    for m in messages:
        bucket = sessions.setdefault(m.session_id, {"session_id": m.session_id, "messages": []})
        if len(bucket["messages"]) >= MAX_CHAT_PER_SESSION:
            continue
        bucket["messages"].append({
            "role": m.role,
            "content": (m.content or "")[:MAX_CHAT_MESSAGE_CHARS],
        })

    stats = {
        "activity_count": len(activities),
        "chat_message_count": len(messages),
        "session_count": len(sessions),
        "todo_done_count": len(todos_done),
        "schedule_count": len(schedule),
        "event_types": event_types,
        "top_apps": [
            {"app": app, "minutes": minutes}
            for app, minutes in sorted(app_minutes.items(), key=lambda x: -x[1])[:8]
        ],
    }

    top_apps_text = "、".join(f"{x['app']}({x['minutes']}分钟)" for x in stats["top_apps"]) or "无"
    digest_parts = [
        f"日期: {day.isoformat()}",
        f"活动事件: {len(activities)} 条；常用应用: {top_apps_text}",
        "活动明细:",
        *(["  " + line for line in activity_lines] or ["  无"]),
        f"完成待办 ({len(todos_done)}): " + ("、".join(t.title for t in todos_done) or "无"),
        f"日程 ({len(schedule)}): " + (
            "、".join(f"{e.start_time.strftime('%H:%M')} {e.title}" for e in schedule) or "无"
        ),
    ]
    if sessions:
        digest_parts.append("当天会话:")
        for s in sessions.values():
            digest_parts.append(f"[{s['session_id']}]")
            for m in s["messages"]:
                role = "用户" if m["role"] == "user" else "助理"
                digest_parts.append(f"  {role}: {m['content']}")
    digest = "\n".join(digest_parts)[:MAX_DIGEST_CHARS]

    return {
        "day": day.isoformat(),
        "stats": stats,
        "activities": activity_lines,
        "sessions": list(sessions.values()),
        "session_ids": list(sessions.keys()),
        "todos_done": [t.title for t in todos_done],
        "schedule": [
            {"time": e.start_time.strftime("%H:%M"), "title": e.title}
            for e in schedule
        ],
        "digest": digest,
    }


def _fallback_summary(data: dict) -> dict:
    stats = data["stats"]
    bits = []
    if stats["activity_count"]:
        bits.append(f"记录了 {stats['activity_count']} 条活动")
    if stats["chat_message_count"]:
        bits.append(f"进行了 {stats['chat_message_count']} 条对话")
    if stats["todo_done_count"]:
        bits.append(f"完成 {stats['todo_done_count']} 项待办")
    if stats["schedule_count"]:
        bits.append(f"有 {stats['schedule_count']} 个日程")

    summary = "今天" + "，".join(bits) + "。" if bits else "今天没有可回顾的记录。"
    top_apps = stats.get("top_apps") or []
    if top_apps:
        summary += f"主要使用 {top_apps[0]['app']}（{top_apps[0]['minutes']} 分钟）。"
    if data["todos_done"]:
        summary += "完成的事项：" + "、".join(data["todos_done"][:3]) + "。"
    activity_snippets = [
        line.split(": ", 1)[1][:80]
        for line in data.get("activities", [])
        if ": " in line and line.split(": ", 1)[1].strip()
    ][:3]
    if activity_snippets:
        summary += "记录：" + "；".join(activity_snippets) + "。"

    highlights = list(data["todos_done"][:5])
    if data["schedule"]:
        highlights.extend(f"{x['time']} {x['title']}" for x in data["schedule"][:5])
    return {
        "summary": summary,
        "highlights": highlights,
        "patterns": [],
        "suggestions": [],
    }


async def _llm_insight(data: dict) -> dict | None:
    if not settings.llm_api_key:
        return None
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": (
                    "你是用户的私人 AI 助理。下面是用户【今天】的活动与对话记录。"
                    "请只基于这些记录生成当日回顾，不要编造，也不要重复分析历史。"
                    "只返回 JSON，格式: "
                    '{"summary": "2-4 句中文回顾，说明今天做了什么、进展如何", '
                    '"highlights": ["今天完成或发生的关键事项"], '
                    '"patterns": ["当天观察到的节奏/习惯/问题，没有就空数组"], '
                    '"suggestions": [{"text": "可执行建议", "action": "todo|schedule|none"}]}。'
                    "建议要具体、少量（0-3 条）。不要输出其他内容。"
                )},
                {"role": "user", "content": data["digest"]},
            ],
            temperature=0.3,
        )
        raw = resp.choices[0].message.content or ""
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        parsed = json.loads(m.group(0))
        if not isinstance(parsed, dict):
            return None
        return {
            "summary": str(parsed.get("summary") or "").strip(),
            "highlights": [str(x) for x in (parsed.get("highlights") or []) if str(x).strip()],
            "patterns": [str(x) for x in (parsed.get("patterns") or []) if str(x).strip()],
            "suggestions": [
                x if isinstance(x, dict) else {"text": str(x), "action": "none"}
                for x in (parsed.get("suggestions") or [])
            ],
        }
    except Exception as e:
        print(f"[insights] llm error: {e}")
        return None


async def generate_daily_insight(
    user_id: int,
    day: date,
    force: bool = False,
    notify: bool = False,
) -> "DailyInsight | None":
    """Generate (or reuse) one user's review for one day.

    Returns ``None`` when the day has no activity, chat, todo or schedule data.
    """
    from core.ai.insight_models import DailyInsight
    from core.database.session import async_session

    async with async_session() as db:
        existing = (await db.execute(
            select(DailyInsight).where(
                DailyInsight.user_id == user_id,
                DailyInsight.day == day,
            )
        )).scalar_one_or_none()
        if existing is not None and not force:
            return existing

    data = await collect_day_data(user_id, day)
    stats = data["stats"]
    if not any((
        stats["activity_count"],
        stats["chat_message_count"],
        stats["todo_done_count"],
        stats["schedule_count"],
    )):
        return None

    payload = await _llm_insight(data) or _fallback_summary(data)
    if not payload.get("summary"):
        payload = _fallback_summary(data)

    async with async_session() as db:
        row = (await db.execute(
            select(DailyInsight).where(
                DailyInsight.user_id == user_id,
                DailyInsight.day == day,
            )
        )).scalar_one_or_none()
        if row is None:
            row = DailyInsight(user_id=user_id, day=day)
            db.add(row)
        row.summary = payload["summary"]
        row.highlights = payload.get("highlights") or []
        row.patterns = payload.get("patterns") or []
        row.suggestions = payload.get("suggestions") or []
        row.stats = stats
        row.session_ids = data["session_ids"]
        row.generated_at = datetime.utcnow()
        await db.flush()
        await db.refresh(row)

        if notify:
            await _notify_review(db, user_id, row)

        await db.commit()
        await db.refresh(row)
        return row


async def _notify_review(db, user_id: int, row) -> None:
    try:
        from plugins.notifications.backend.router import notify_user
        from plugins.notifications.backend.service import create_notification

        n = await create_notification(
            db,
            user_id,
            "🌙 今日回顾",
            (row.summary or "")[:500],
            "daily_review",
            "/insights",
            actions=[{"key": "open", "label": "查看回顾", "kind": "open", "link": "/insights"}],
            dedupe_key=f"daily_review:{row.day.isoformat()}",
        )
        await db.flush()
        await notify_user(user_id, {
            "type": "new_notification",
            "id": n.id,
            "title": "🌙 今日回顾",
            "body": (row.summary or "")[:500],
            "link": "/insights",
        })
    except Exception as e:
        print(f"[insights] notify error: {e}")


async def get_recent_insights(user_id: int, days: int = 7) -> list:
    from core.ai.insight_models import DailyInsight
    from core.database.session import async_session

    async with async_session() as db:
        r = await db.execute(
            select(DailyInsight)
            .where(DailyInsight.user_id == user_id)
            .order_by(DailyInsight.day.desc())
            .limit(max(1, days))
        )
        return list(r.scalars().all())


async def ensure_daily_insight(user_id: int, day: date):
    """Return the day's review, generating it if missing (no notification)."""
    from core.ai.insight_models import DailyInsight
    from core.database.session import async_session

    async with async_session() as db:
        existing = (await db.execute(
            select(DailyInsight).where(
                DailyInsight.user_id == user_id,
                DailyInsight.day == day,
            )
        )).scalar_one_or_none()
        if existing is not None:
            return existing
    return await generate_daily_insight(user_id, day, notify=False)


async def build_insight_context(user_id: int, days: int = 2) -> str | None:
    """Short review block injected into the bot's system context."""
    try:
        rows = await get_recent_insights(user_id, days)
        if not rows:
            return None
        lines = []
        for r in rows:
            label = "今日回顾" if r.day == date.today() else f"{r.day.isoformat()} 回顾"
            lines.append(f"{label}: {r.summary}")
            for s in (r.suggestions or [])[:2]:
                if isinstance(s, dict) and s.get("text"):
                    lines.append(f"- 建议: {s['text']}")
        return ("【最近回顾】\n" + "\n".join(lines))[:800]
    except Exception:
        return None
