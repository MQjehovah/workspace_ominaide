"""Weekly review pipeline.

A weekly review is generated from the stored daily reviews plus the week's
todos/schedule/mail, then persisted in ``weekly_reviews`` so it can be opened
again at any time. The hourly daily brief is intentionally not persisted; this
is the long-term review record.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from sqlalchemy import or_, select

from core.ai.llm import llm_json
from core.ai.scenarios._time import day_bounds
from core.logging import get_logger

log = get_logger(__name__)


def _week_bounds(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    return today - timedelta(days=6), today


async def _weekly_review_data(
    user_id: int,
    weeks: int = 1,
    *,
    bot=None,
    extra_system: str | None = None,
) -> dict:
    from core.ai.daily_insights import get_recent_insights
    from core.database.session import async_session
    from plugins.mail.backend.models import MailMessage
    from plugins.schedule.backend.models import Event
    from plugins.todo.backend.models import PluginTodoItem

    days = max(7, weeks * 7)
    today = date.today()
    start_day = today - timedelta(days=days - 1)
    start_dt, _ = day_bounds(start_day)
    _, end_dt = day_bounds(today)

    insights = [
        row for row in await get_recent_insights(user_id, days)
        if row.day >= start_day
    ]

    async with async_session() as db:
        done = list((await db.execute(
            select(PluginTodoItem).where(
                PluginTodoItem.user_id == user_id,
                PluginTodoItem.status == "done",
                PluginTodoItem.updated_at >= start_dt,
            ).order_by(PluginTodoItem.updated_at.desc()).limit(50)
        )).scalars().all())
        pending = list((await db.execute(
            select(PluginTodoItem).where(
                PluginTodoItem.user_id == user_id,
                PluginTodoItem.status == "pending",
            ).order_by(PluginTodoItem.due_date).limit(50)
        )).scalars().all())
        next_events = list((await db.execute(
            select(Event).where(
                Event.user_id == user_id,
                Event.start_time >= datetime.now(),
                Event.start_time < datetime.now() + timedelta(days=7),
            ).order_by(Event.start_time).limit(20)
        )).scalars().all())
        important_mail = list((await db.execute(
            select(MailMessage).where(
                MailMessage.user_id == user_id,
                MailMessage.important == True,  # noqa: E712
                or_(MailMessage.date >= start_dt, MailMessage.created_at >= start_dt),
            ).limit(30)
        )).scalars().all())

    wins: list[str] = []
    for row in insights:
        wins.extend(str(x) for x in (row.highlights or []) if str(x).strip())
    wins.extend(t.title for t in done[:8])
    wins = list(dict.fromkeys(wins))[:10]

    overdue = [
        t.title for t in pending
        if t.due_date and t.due_date < datetime.now()
    ][:5]
    risks = overdue
    in_progress = [t.title for t in pending[:8]]
    next_week = [
        f"{(e.start_time.strftime('%m-%d %H:%M') if e.start_time else '')} {e.title}"
        for e in next_events
    ]

    insight_text = "；".join(row.summary for row in insights if row.summary)
    summary = (
        f"本周完成 {len(done)} 项待办，还有 {len(pending)} 项待推进。"
        + (f" 回顾：{insight_text}" if insight_text else "")
        + (f" 逾期：{'、'.join(overdue)}。" if overdue else "")
    )[:1200]

    enriched = await llm_json(
        "基于本周数据写一份中文周报，"
        "包括成果、进行中、风险、下周重点。不要编造。"
        '只返回 JSON: {"summary": "3-5 句总结", "wins": ["成果"], '
        '"in_progress": ["进行中"], "risks": ["风险"], "next_week": ["下周重点"]}。',
        json.dumps({
            "period": [start_day.isoformat(), today.isoformat()],
            "insights": [
                {"day": row.day.isoformat(), "summary": row.summary,
                 "highlights": row.highlights, "patterns": row.patterns}
                for row in insights
            ],
            "todos_done": [t.title for t in done],
            "todos_pending": [t.title for t in pending],
            "events_next_week": next_week,
            "important_mail": [m.subject for m in important_mail],
        }, ensure_ascii=False),
        bot=bot,
        extra_system=extra_system,
    )
    if enriched:
        if isinstance(enriched.get("summary"), str) and enriched["summary"].strip():
            summary = enriched["summary"].strip()
        if isinstance(enriched.get("wins"), list) and enriched["wins"]:
            wins = [str(x) for x in enriched["wins"] if str(x).strip()]
        if isinstance(enriched.get("in_progress"), list) and enriched["in_progress"]:
            in_progress = [str(x) for x in enriched["in_progress"] if str(x).strip()]
        if isinstance(enriched.get("risks"), list) and enriched["risks"]:
            risks = [str(x) for x in enriched["risks"] if str(x).strip()]
        if isinstance(enriched.get("next_week"), list) and enriched["next_week"]:
            next_week = [str(x) for x in enriched["next_week"] if str(x).strip()]

    return {
        "period": {"start": start_day.isoformat(), "end": today.isoformat()},
        "summary": summary,
        "wins": wins,
        "in_progress": in_progress,
        "risks": risks,
        "next_week": next_week,
        "stats": {
            "insight_days": len(insights),
            "todos_done": len(done),
            "todos_pending": len(pending),
            "events_next_week": len(next_events),
            "important_mail": len(important_mail),
        },
    }


async def generate_weekly_review(
    user_id: int,
    *,
    weeks: int = 1,
    bot=None,
    force: bool = False,
    notify: bool = False,
):
    """Generate or reuse one user's review for the current week."""
    from core.ai.insight_models import WeeklyReview
    from core.database.session import async_session
    from core.skills.loader import get_skill

    week_start, week_end = _week_bounds()

    async with async_session() as db:
        existing = (await db.execute(
            select(WeeklyReview).where(
                WeeklyReview.user_id == user_id,
                WeeklyReview.week_start == week_start,
            )
        )).scalar_one_or_none()
        if existing is not None and not force:
            return existing

    skill = get_skill("weekly-review")
    data = await _weekly_review_data(
        user_id,
        weeks=weeks,
        bot=bot,
        extra_system=skill.body if skill else None,
    )

    async with async_session() as db:
        row = (await db.execute(
            select(WeeklyReview).where(
                WeeklyReview.user_id == user_id,
                WeeklyReview.week_start == week_start,
            )
        )).scalar_one_or_none()
        if row is None:
            row = WeeklyReview(user_id=user_id, week_start=week_start, week_end=week_end)
            db.add(row)
        row.week_end = week_end
        row.summary = str(data.get("summary") or "")
        row.wins = data.get("wins") or []
        row.in_progress = data.get("in_progress") or []
        row.risks = data.get("risks") or []
        row.next_week = data.get("next_week") or []
        row.stats = data.get("stats") or {}
        row.generated_at = datetime.utcnow()
        await db.flush()
        await db.refresh(row)
        if notify:
            await _notify_weekly_review(db, user_id, row)
        await db.commit()
        await db.refresh(row)
        return row


async def _notify_weekly_review(db, user_id: int, row) -> None:
    try:
        from plugins.notifications.backend.router import notify_user
        from plugins.notifications.backend.service import create_notification

        n = await create_notification(
            db,
            user_id,
            "📅 本周回顾",
            (row.summary or "")[:500],
            "weekly_review",
            "/insights",
            actions=[{"key": "open", "label": "查看回顾", "kind": "open", "link": "/insights"}],
            dedupe_key=f"weekly_review:{row.week_start.isoformat()}",
        )
        await db.flush()
        await notify_user(user_id, {
            "type": "new_notification",
            "id": n.id,
            "title": "📅 本周回顾",
            "body": (row.summary or "")[:500],
            "link": "/insights",
        })
    except Exception as e:
        log.warning(f"[weekly] notify error: {e}")


async def get_recent_weekly_reviews(user_id: int, limit: int = 8) -> list:
    from core.ai.insight_models import WeeklyReview
    from core.database.session import async_session

    async with async_session() as db:
        rows = await db.execute(
            select(WeeklyReview)
            .where(WeeklyReview.user_id == user_id)
            .order_by(WeeklyReview.week_start.desc())
            .limit(max(1, limit))
        )
        return list(rows.scalars().all())


async def get_latest_weekly_review(user_id: int):
    rows = await get_recent_weekly_reviews(user_id, 1)
    return rows[0] if rows else None
