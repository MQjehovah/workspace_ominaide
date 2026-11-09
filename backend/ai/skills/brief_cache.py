"""Hourly-rendered daily brief cache.

The hourly job renders one snapshot per user using the default bot. The
snapshot contains the brief summary and the workbench quick prompts, so both
surfaces read the same LLM result and request handlers never call the model.
"""

from __future__ import annotations

from datetime import date, datetime

from core.cache import get_json, set_json
from core.logging import get_logger

log = get_logger(__name__)

SKILL_KEY = "daily-brief"
TTL_SECONDS = 3700


def _key(user_id: int, day: date) -> str:
    return f"brief:daily:{user_id}:{day.isoformat()}"


async def get_cached(user_id: int, day: date | None = None) -> dict | None:
    day = day or date.today()
    cached = await get_json(_key(user_id, day))
    return cached if isinstance(cached, dict) and cached.get("summary") is not None else None


async def generate(
    user_id: int,
    *,
    bot=None,
    day: date | None = None,
    refresh: bool = False,
) -> dict:
    """Return the cached brief, rendering it only when needed."""
    from ai.scenarios.daily_brief import daily_brief
    from ai.skills.loader import get_skill

    day = day or date.today()
    if not refresh:
        cached = await get_cached(user_id, day)
        if cached is not None:
            return cached

    skill = get_skill(SKILL_KEY)
    output = await daily_brief(
        user_id,
        day=day,
        bot=bot,
        extra_system=skill.body if skill else None,
    )
    await set_json(_key(user_id, day), output, ttl_seconds=TTL_SECONDS)
    return output


async def refresh_user(user_id: int) -> dict:
    from ai.bots.registry import get_active_bot

    bot = await get_active_bot(user_id)
    return await generate(user_id, bot=bot, refresh=True)


async def all_user_ids() -> list[int]:
    from sqlalchemy import select

    from core.auth.domain.models import User
    from core.database.session import async_session

    async with async_session() as db:
        return list((await db.execute(select(User.id).order_by(User.id))).scalars().all())


async def refresh_all() -> dict:
    """Compatibility helper used by tests or manual warm-up."""
    generated = 0
    failed = 0
    for user_id in await all_user_ids():
        try:
            await refresh_user(user_id)
            generated += 1
        except Exception as exc:
            failed += 1
            log.warning("[brief] render failed for user %s: %s", user_id, exc)
    return {"generated": generated, "failed": failed}


def hour_key(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y%m%d%H")


async def send_briefing(user_id: int) -> dict:
    """Render a fresh brief and deliver it as a notification."""
    from core.database.session import async_session
    from plugins.notifications.backend.router import notify_user
    from plugins.notifications.backend.service import create_notification

    payload = await refresh_user(user_id)
    title = "☀️ 今日简报"
    body = str(payload.get("summary") or "")
    async with async_session() as db:
        await create_notification(
            db,
            user_id,
            title,
            body,
            "briefing",
            "/chat",
            actions=[{"key": "open", "label": "打开对话", "kind": "open", "link": "/chat"}],
            dedupe_key=f"briefing:{payload.get('day')}:{int(datetime.now().timestamp() // 60)}",
        )
        await db.commit()
    try:
        await notify_user(user_id, {"type": "new_notification", "title": title, "link": "/chat"})
    except Exception:
        pass
    return payload
