"""Built-in skill handlers. Each handler is the deterministic/domain part of a
SKILL.md capability; the runtime supplies the bot, input and loaded skill."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Awaitable, Callable

from core.bots.models import Bot
from core.skills.loader import SkillDefinition


@dataclass
class SkillContext:
    user_id: int
    bot: Bot
    skill: SkillDefinition
    input: dict[str, Any]
    run_id: int | None = None


async def _daily_brief(ctx: SkillContext) -> dict:
    from core.cos.service import daily_brief

    raw_day = ctx.input.get("day")
    day = None
    if raw_day:
        try:
            day = date.fromisoformat(str(raw_day))
        except ValueError:
            raise ValueError("day 必须是 YYYY-MM-DD")
    return await daily_brief(
        ctx.user_id,
        day=day,
        bot=ctx.bot,
        extra_system=ctx.skill.body,
    )


async def _meeting_prepare(ctx: SkillContext) -> dict:
    from core.cos.service import meeting_prep

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


async def _weekly_review(ctx: SkillContext) -> dict:
    from core.cos.service import weekly_review

    try:
        weeks = max(1, min(int(ctx.input.get("weeks") or 1), 4))
    except (TypeError, ValueError):
        weeks = 1
    return await weekly_review(
        ctx.user_id,
        weeks=weeks,
        bot=ctx.bot,
        extra_system=ctx.skill.body,
    )


HANDLERS: dict[str, Callable[[SkillContext], Awaitable[dict]]] = {
    "daily-brief": _daily_brief,
    "meeting-prepare": _meeting_prepare,
    "weekly-review": _weekly_review,
}
