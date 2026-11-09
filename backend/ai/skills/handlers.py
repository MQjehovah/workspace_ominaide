"""Built-in skill handlers. Each handler is the deterministic/domain part of a
SKILL.md capability; the runtime supplies the bot, input and loaded skill."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Awaitable, Callable

from ai.bots.models import Bot
from ai.skills.loader import SkillDefinition


@dataclass
class SkillContext:
    user_id: int
    bot: Bot
    skill: SkillDefinition
    input: dict[str, Any]
    run_id: int | None = None


async def _daily_brief(ctx: SkillContext) -> dict:
    from ai.skills import brief_cache

    raw_day = ctx.input.get("day")
    day = None
    if raw_day:
        try:
            day = date.fromisoformat(str(raw_day))
        except ValueError:
            raise ValueError("day 必须是 YYYY-MM-DD")
    return await brief_cache.generate(
        ctx.user_id,
        bot=ctx.bot,
        day=day,
        refresh=bool(ctx.input.get("refresh")),
    )


async def _meeting_prepare(ctx: SkillContext) -> dict:
    from ai.scenarios.meeting_prep import meeting_prep

    attendees = ctx.input.get("attendees") or []
    if isinstance(attendees, str):
        attendees = [x.strip() for x in attendees.split(",") if x.strip()]
    return await meeting_prep(
        ctx.user_id,
        title=str(ctx.input.get("title") or ""),
        start=ctx.input.get("start"),
        attendees=[str(x) for x in attendees],
        query=ctx.input.get("query"),
        bot=ctx.bot,
        extra_system=ctx.skill.body,
    )


async def _daily_review(ctx: SkillContext) -> dict:
    from ai.insights.daily import generate_daily_insight

    day = date.today()
    raw_day = ctx.input.get("day")
    if raw_day:
        try:
            day = date.fromisoformat(str(raw_day))
        except ValueError:
            raise ValueError("day 必须是 YYYY-MM-DD")
    row = await generate_daily_insight(
        ctx.user_id,
        day,
        force=bool(ctx.input.get("force", True)),
        notify=bool(ctx.input.get("notify", True)),
    )
    if row is None:
        return {
            "day": day.isoformat(),
            "summary": "",
            "highlights": [],
            "patterns": [],
            "suggestions": [],
            "stats": {},
        }
    return {
        "day": row.day.isoformat(),
        "summary": row.summary,
        "highlights": row.highlights or [],
        "patterns": row.patterns or [],
        "suggestions": row.suggestions or [],
        "stats": row.stats or {},
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
    }


async def _weekly_review(ctx: SkillContext) -> dict:
    from ai.insights.weekly import generate_weekly_review

    try:
        weeks = max(1, min(int(ctx.input.get("weeks") or 1), 4))
    except (TypeError, ValueError):
        weeks = 1
    row = await generate_weekly_review(
        ctx.user_id,
        weeks=weeks,
        bot=ctx.bot,
        force=bool(ctx.input.get("force", True)),
        notify=bool(ctx.input.get("notify", True)),
    )
    return {
        "period": {
            "start": row.week_start.isoformat(),
            "end": row.week_end.isoformat(),
        },
        "summary": row.summary,
        "wins": row.wins or [],
        "in_progress": row.in_progress or [],
        "risks": row.risks or [],
        "next_week": row.next_week or [],
        "stats": row.stats or {},
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
    }


async def _draft_reply(ctx: SkillContext) -> dict:
    from ai.scenarios.draft_reply import draft_reply

    draft = await draft_reply(
        ctx.user_id,
        source=str(ctx.input.get("source") or "mail"),
        message_id=ctx.input.get("message_id"),
        message=ctx.input.get("message"),
        subject=ctx.input.get("subject"),
        tone=str(ctx.input.get("tone") or "professional"),
        instructions=ctx.input.get("instructions"),
        bot=ctx.bot,
        extra_system=ctx.skill.body,
    )
    if draft is None:
        raise ValueError("没有可回复的内容")
    return draft


HANDLERS: dict[str, Callable[[SkillContext], Awaitable[dict]]] = {
    "daily-brief": _daily_brief,
    "daily-review": _daily_review,
    "meeting-prepare": _meeting_prepare,
    "weekly-review": _weekly_review,
    "draft-reply": _draft_reply,
}
