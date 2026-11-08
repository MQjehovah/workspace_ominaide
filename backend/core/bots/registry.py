"""Bot registry: identity lifecycle and the default ``main`` bot.

The default bot is created lazily for every user so existing deployments keep
working: any call without a bot_id resolves to ``main``.
"""
import re
import unicodedata

from sqlalchemy import select, update, delete

from core.config.settings import settings
from core.database.session import async_session
from core.bots.models import Bot, BotMemory

DEFAULT_BOT_SLUG = "main"
DEFAULT_BOT_NAME = "助手"
DEFAULT_BOT_AVATAR = "🤖"
DEFAULT_BOT_ROLE = "个人助理"


class BotNotFound(Exception):
    def __init__(self, bot_id: int | None = None):
        super().__init__(f"Bot not found: {bot_id}")
        self.bot_id = bot_id


class BotConflict(Exception):
    pass


def _slugify(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").strip().lower()
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return (value or "bot")[:64]


async def _unique_slug(db, user_id: int, base: str, exclude_id: int | None = None) -> str:
    slug = _slugify(base)
    candidate = slug
    n = 2
    while True:
        q = select(Bot.id).where(Bot.user_id == user_id, Bot.slug == candidate)
        if exclude_id is not None:
            q = q.where(Bot.id != exclude_id)
        if (await db.execute(q)).scalar_one_or_none() is None:
            return candidate
        candidate = f"{slug}-{n}"
        n += 1


async def _ensure_default(db, user_id: int) -> Bot:
    r = await db.execute(
        select(Bot)
        .where(
            Bot.user_id == user_id,
            Bot.is_default == True,  # noqa: E712
            Bot.status == "active",
        )
        .order_by(Bot.id.asc())
        .limit(1)
    )
    bot = r.scalar_one_or_none()
    if bot is not None:
        return bot

    # Fall back to the well-known ``main`` slug, then promote it.
    r = await db.execute(
        select(Bot).where(Bot.user_id == user_id, Bot.slug == DEFAULT_BOT_SLUG)
    )
    bot = r.scalar_one_or_none()
    if bot is not None:
        bot.is_default = True
        return bot

    bot = Bot(
        user_id=user_id,
        slug=DEFAULT_BOT_SLUG,
        name=DEFAULT_BOT_NAME,
        avatar=DEFAULT_BOT_AVATAR,
        role=DEFAULT_BOT_ROLE,
        system_prompt=settings.assistant_system_prompt,
        temperature=0.7,
        max_turns=60,
        is_default=True,
        status="active",
    )
    db.add(bot)
    await db.flush()
    return bot


async def seed_default_bots() -> None:
    """Create the ``main`` bot for every existing user (startup backfill)."""
    from core.auth.domain.models import User

    async with async_session() as db:
        user_ids = list((await db.execute(select(User.id))).scalars().all())
        for uid in user_ids:
            await _ensure_default(db, uid)
        await db.commit()


async def get_or_create_default_bot(user_id: int) -> Bot:
    async with async_session() as db:
        bot = await _ensure_default(db, user_id)
        await db.commit()
        await db.refresh(bot)
    return bot


async def get_active_bot(user_id: int, bot_id: int | None = None) -> Bot:
    made_default = False
    async with async_session() as db:
        if bot_id is None:
            bot = await _ensure_default(db, user_id)
            await db.commit()
            await db.refresh(bot)
            made_default = True
        else:
            bot = (
                await db.execute(
                    select(Bot).where(Bot.id == bot_id, Bot.user_id == user_id)
                )
            ).scalar_one_or_none()
            if bot is None or bot.status != "active":
                raise BotNotFound(bot_id)

    return bot


async def list_bots(user_id: int) -> list[Bot]:
    async with async_session() as db:
        await _ensure_default(db, user_id)
        await db.commit()
        rows = await db.execute(
            select(Bot)
            .where(Bot.user_id == user_id, Bot.status != "archived")
            .order_by(Bot.is_default.desc(), Bot.id.asc())
        )
        return list(rows.scalars().all())


async def create_bot(user_id: int, data) -> Bot:
    async with async_session() as db:
        slug = await _unique_slug(db, user_id, data.slug or data.name)
        if data.is_default:
            await db.execute(
                update(Bot).where(Bot.user_id == user_id).values(is_default=False)
            )
        bot = Bot(
            user_id=user_id,
            slug=slug,
            name=data.name,
            avatar=data.avatar,
            role=data.role,
            system_prompt=data.system_prompt or settings.assistant_system_prompt,
            model=data.model,
            temperature=data.temperature,
            allowed_tools=data.allowed_tools,
            pinned_tools=getattr(data, "pinned_tools", None),
            risk_policy=data.risk_policy,
            max_turns=data.max_turns,
            token_budget=data.token_budget,
            is_default=data.is_default,
            status="active",
        )
        db.add(bot)
        await db.commit()
        await db.refresh(bot)
        return bot


async def update_bot(user_id: int, bot_id: int, data) -> Bot:
    async with async_session() as db:
        bot = (
            await db.execute(
                select(Bot).where(Bot.id == bot_id, Bot.user_id == user_id)
            )
        ).scalar_one_or_none()
        if bot is None:
            raise BotNotFound(bot_id)

        fields = data.model_dump(exclude_unset=True)
        if "slug" in fields and fields["slug"]:
            fields["slug"] = await _unique_slug(db, user_id, fields["slug"], exclude_id=bot_id)
        if fields.pop("is_default", None) is True:
            await db.execute(
                update(Bot).where(Bot.user_id == user_id, Bot.id != bot_id).values(is_default=False)
            )
            fields["is_default"] = True
        if fields.get("status") == "archived" and bot.is_default:
            raise BotConflict("cannot archive the default bot")

        for key, value in fields.items():
            setattr(bot, key, value)

        await db.commit()
        await db.refresh(bot)
        return bot


async def delete_bot(user_id: int, bot_id: int, purge: bool = False) -> None:
    async with async_session() as db:
        bot = (
            await db.execute(
                select(Bot).where(Bot.id == bot_id, Bot.user_id == user_id)
            )
        ).scalar_one_or_none()
        if bot is None:
            raise BotNotFound(bot_id)
        if bot.is_default:
            raise BotConflict("cannot delete the default bot")

        if not purge:
            bot.status = "archived"
            await db.commit()
            return

        memories = list(
            (await db.execute(select(BotMemory).where(BotMemory.bot_id == bot_id)))
            .scalars()
            .all()
        )
        for mem in memories:
            try:
                from core.ai import vector_store
                await vector_store.delete("entities", f"mem_{bot_id}_{mem.id}")
            except Exception:
                pass
        await db.execute(delete(BotMemory).where(BotMemory.bot_id == bot_id))
        await db.execute(delete(Bot).where(Bot.id == bot_id))
        await db.commit()
