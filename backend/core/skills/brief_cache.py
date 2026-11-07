"""Hourly-rendered daily brief cache.

Rendering a brief collects mail/schedule/todo/source context and optionally
calls the LLM, which is too slow for a mobile first paint. The scheduler
renders every user's default bot once per hour; the skill endpoint reads that
snapshot. A cache miss (new user or newly selected bot) renders once and then
stores the result, so later requests are served from cache.
"""

from __future__ import annotations

from datetime import date

from core.cache import get_json, set_json
from core.logging import get_logger

log = get_logger(__name__)

SKILL_KEY = "daily-brief"
TTL_SECONDS = 3700


def _key(user_id: int, bot_id: int | None, day: date) -> str:
    return f"brief:daily:{user_id}:{bot_id or 0}:{day.isoformat()}"


async def generate(
    user_id: int,
    *,
    bot,
    day: date | None = None,
    refresh: bool = False,
) -> dict:
    """Return the cached brief, rendering it only when needed."""
    from core.cos.service import daily_brief
    from core.skills.loader import get_skill

    day = day or date.today()
    key = _key(user_id, getattr(bot, "id", None), day)
    if not refresh:
        cached = await get_json(key)
        if isinstance(cached, dict) and cached.get("summary"):
            return cached

    skill = get_skill(SKILL_KEY)
    output = await daily_brief(
        user_id,
        day=day,
        bot=bot,
        extra_system=skill.body if skill else None,
    )
    await set_json(key, output, ttl_seconds=TTL_SECONDS)
    return output


async def refresh_all() -> dict:
    """Render the hourly snapshot for every active bot.

    Users can switch bots in the app, so warming only the default bot would
    send a cache miss to the LLM on the next request.
    """
    from sqlalchemy import select

    from core.bots.models import Bot
    from core.database.session import async_session
    from core.skills import runtime

    async with async_session() as db:
        bots = list((await db.execute(
            select(Bot).where(Bot.status == "active")
        )).scalars().all())

    generated = 0
    failed = 0
    for bot in bots:
        try:
            if not await runtime.is_skill_enabled(bot, SKILL_KEY):
                continue
            await generate(int(bot.user_id), bot=bot, refresh=True)
            generated += 1
        except Exception as exc:
            failed += 1
            log.warning(
                "[brief] render failed for user %s bot %s: %s",
                getattr(bot, "user_id", "?"),
                getattr(bot, "id", "?"),
                exc,
            )
    return {"generated": generated, "failed": failed}
