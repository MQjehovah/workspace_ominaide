"""Compatibility wrapper around bot-scoped context.

New code should call ``ai.bots.memory.build_bot_context(user_id, bot, query)``
with an explicit bot. This wrapper resolves the user's default bot for older
call sites.
"""
from ai.bots.memory import build_bot_context


async def build_context(user_id: int, query: str = "") -> str | None:
    try:
        from ai.bots.registry import get_or_create_default_bot

        bot = await get_or_create_default_bot(user_id)
    except Exception:
        bot = None
    return await build_bot_context(user_id, bot, query)
