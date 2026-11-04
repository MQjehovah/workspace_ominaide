"""Bot routines: cron schedules and event triggers.

The loop runs in the FastAPI lifespan alongside the existing system scheduler.
Cron expressions are the standard 5-field form (minute hour dom month dow).
"""
import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select, delete, update

from core.bots import runner
from core.bots.models import Bot, BotRoutine
from core.config.settings import settings
from core.database.session import async_session

MORNING_ROUTINE = "morning_brief"


def _parse_field(expr: str, lo: int, hi: int) -> set[int]:
    values: set[int] = set()
    for part in expr.split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        if "/" in part:
            part, raw_step = part.split("/", 1)
            step = int(raw_step)
            if step <= 0:
                raise ValueError("cron step must be positive")
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(part)
        if start < lo or end > hi or start > end:
            raise ValueError(f"cron field out of range: {expr}")
        values.update(range(start, end + 1, step))
    if not values:
        raise ValueError(f"empty cron field: {expr}")
    return values


def parse_cron(expr: str) -> dict:
    parts = (expr or "").split()
    if len(parts) != 5:
        raise ValueError("cron expression must have 5 fields")
    minute, hour, dom, month, dow = parts
    dow_values = _parse_field(dow, 0, 7)
    if 7 in dow_values:
        dow_values.discard(7)
        dow_values.add(0)
    return {
        "minute": _parse_field(minute, 0, 59),
        "hour": _parse_field(hour, 0, 23),
        "dom": _parse_field(dom, 1, 31),
        "month": _parse_field(month, 1, 12),
        "dow": dow_values,
        "dom_any": dom.strip() == "*",
        "dow_any": dow.strip() == "*",
    }


def cron_matches(expr: str, when: datetime) -> bool:
    c = parse_cron(expr)
    if when.minute not in c["minute"] or when.hour not in c["hour"]:
        return False
    if when.month not in c["month"]:
        return False
    dow = (when.weekday() + 1) % 7  # Monday=0 -> 1, Sunday=6 -> 0
    dom_ok = when.day in c["dom"]
    dow_ok = dow in c["dow"]
    if c["dom_any"] and c["dow_any"]:
        return True
    if c["dom_any"]:
        return dow_ok
    if c["dow_any"]:
        return dom_ok
    return dom_ok or dow_ok


def next_run(expr: str, after: datetime | None = None) -> datetime:
    when = (after or datetime.now()).replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = when + timedelta(days=366)
    while when < limit:
        if cron_matches(expr, when):
            return when
        when += timedelta(minutes=1)
    raise ValueError("cron expression has no run time within one year")


async def list_routines(user_id: int, bot_id: int | None = None) -> list[BotRoutine]:
    async with async_session() as db:
        q = select(BotRoutine).where(BotRoutine.user_id == user_id)
        if bot_id is not None:
            q = q.where(BotRoutine.bot_id == bot_id)
        q = q.order_by(BotRoutine.id.desc())
        return list((await db.execute(q)).scalars().all())


async def get_routine(user_id: int, routine_id: int) -> BotRoutine | None:
    async with async_session() as db:
        return (
            await db.execute(
                select(BotRoutine).where(
                    BotRoutine.id == routine_id, BotRoutine.user_id == user_id
                )
            )
        ).scalar_one_or_none()


async def create_routine(user_id: int, bot_id: int, name: str, *, trigger_type: str = "cron",
                         cron_expr: str | None = None, event_type: str | None = None,
                         event_filter: dict | None = None, prompt: str | None = None,
                         enabled: bool = True) -> BotRoutine:
    trigger_type = (trigger_type or "cron").lower()
    if trigger_type not in ("cron", "event", "manual"):
        raise ValueError("trigger_type must be cron/event/manual")
    nxt = None
    if trigger_type == "cron":
        if not cron_expr:
            raise ValueError("cron_expr is required for cron routines")
        nxt = next_run(cron_expr)
    if trigger_type == "event" and not event_type:
        raise ValueError("event_type is required for event routines")

    async with async_session() as db:
        bot = (
            await db.execute(
                select(Bot).where(Bot.id == bot_id, Bot.user_id == user_id)
            )
        ).scalar_one_or_none()
        if bot is None:
            raise ValueError("bot not found")
        routine = BotRoutine(
            bot_id=bot_id,
            user_id=user_id,
            name=(name or "routine")[:120],
            trigger_type=trigger_type,
            cron_expr=cron_expr,
            event_type=event_type,
            event_filter=event_filter,
            prompt=prompt,
            enabled=enabled,
            next_run_at=nxt,
        )
        db.add(routine)
        await db.commit()
        await db.refresh(routine)
        return routine


async def update_routine(user_id: int, routine_id: int, data: dict) -> BotRoutine | None:
    async with async_session() as db:
        routine = (
            await db.execute(
                select(BotRoutine).where(
                    BotRoutine.id == routine_id, BotRoutine.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if routine is None:
            return None

        if "trigger_type" in data and data["trigger_type"]:
            trigger_type = str(data["trigger_type"]).lower()
            if trigger_type not in ("cron", "event", "manual"):
                raise ValueError("trigger_type must be cron/event/manual")
            routine.trigger_type = trigger_type
        if "cron_expr" in data:
            routine.cron_expr = data["cron_expr"]
        if "event_type" in data:
            routine.event_type = data["event_type"]
        if "event_filter" in data:
            routine.event_filter = data["event_filter"]
        if "name" in data and data["name"]:
            routine.name = str(data["name"])[:120]
        if "prompt" in data:
            routine.prompt = data["prompt"]
        if "enabled" in data:
            routine.enabled = bool(data["enabled"])

        if routine.trigger_type == "cron":
            if not routine.cron_expr:
                raise ValueError("cron_expr is required for cron routines")
            routine.next_run_at = next_run(routine.cron_expr)
        elif routine.trigger_type == "event":
            if not routine.event_type:
                raise ValueError("event_type is required for event routines")
            routine.next_run_at = None

        await db.commit()
        await db.refresh(routine)
        return routine


async def delete_routine(user_id: int, routine_id: int) -> bool:
    async with async_session() as db:
        res = await db.execute(
            delete(BotRoutine).where(
                BotRoutine.id == routine_id, BotRoutine.user_id == user_id
            )
        )
        await db.commit()
        return bool(res.rowcount)


async def has_enabled_routine(user_id: int, name: str) -> bool:
    async with async_session() as db:
        routine = (
            await db.execute(
                select(BotRoutine).where(
                    BotRoutine.user_id == user_id,
                    BotRoutine.name == name,
                    BotRoutine.enabled == True,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        return routine is not None


async def run_routine_now(user_id: int, routine_id: int):
    routine = await get_routine(user_id, routine_id)
    if routine is None:
        return None
    async with async_session() as db:
        bot = (
            await db.execute(select(Bot).where(Bot.id == routine.bot_id))
        ).scalar_one_or_none()
    if bot is None:
        return None
    run = await runner.create_run(
        user_id,
        bot,
        routine.prompt or routine.name,
        trigger="manual",
        routine_id=routine.id,
        idempotency_key=f"routine:{routine.id}:manual:{datetime.utcnow().isoformat(timespec='seconds')}",
    )
    return run


async def routine_loop() -> None:
    """Every 30s, fire due cron routines."""
    while True:
        try:
            await _tick()
        except Exception as e:
            print(f"[bots.routines] loop error: {e}")
        await asyncio.sleep(30)


async def _tick() -> None:
    now = datetime.now().replace(second=0, microsecond=0)
    due: list[BotRoutine] = []
    async with async_session() as db:
        rows = list(
            (
                await db.execute(
                    select(BotRoutine).where(
                        BotRoutine.enabled == True,  # noqa: E712
                        BotRoutine.trigger_type == "cron",
                    )
                )
            ).scalars().all()
        )
        for r in rows:
            if r.next_run_at is None or r.next_run_at <= now:
                due.append(r)

    for r in due:
        try:
            async with async_session() as db:
                bot = (
                    await db.execute(select(Bot).where(Bot.id == r.bot_id))
                ).scalar_one_or_none()
            if bot is None or bot.status != "active":
                await _mark_tick(r.id, None, "no_bot")
                continue
            key = f"routine:{r.id}:{now.strftime('%Y%m%d%H%M')}"
            await runner.create_run(
                r.user_id,
                bot,
                r.prompt or r.name,
                trigger="cron",
                routine_id=r.id,
                idempotency_key=key,
            )
            await _mark_tick(r.id, next_run(r.cron_expr, now), "queued")
        except Exception as e:
            print(f"[bots.routines] tick {r.id} failed: {e}")
            try:
                await _mark_tick(r.id, datetime.now() + timedelta(hours=1), "error")
            except Exception:
                pass


async def _mark_tick(routine_id: int, next_at: datetime | None, status: str) -> None:
    async with async_session() as db:
        values = {"last_run_at": datetime.now(), "last_status": status}
        if next_at is not None:
            values["next_run_at"] = next_at
        await db.execute(
            update(BotRoutine).where(BotRoutine.id == routine_id).values(**values)
        )
        await db.commit()


def register_event_handler() -> None:
    from core.events.bus import subscribe

    subscribe(_on_event)


async def _on_event(event) -> None:
    if event is None:
        return
    try:
        async with async_session() as db:
            rows = list(
                (
                    await db.execute(
                        select(BotRoutine).where(
                            BotRoutine.user_id == event.user_id,
                            BotRoutine.enabled == True,  # noqa: E712
                            BotRoutine.trigger_type == "event",
                            BotRoutine.event_type == event.event_type,
                        )
                    )
                ).scalars().all()
            )
        for r in rows:
            if not _matches_filter(r.event_filter, event):
                continue
            async with async_session() as db:
                bot = (
                    await db.execute(select(Bot).where(Bot.id == r.bot_id))
                ).scalar_one_or_none()
            if bot is None or bot.status != "active":
                continue
            await runner.create_run(
                r.user_id,
                bot,
                r.prompt or r.name,
                trigger="event",
                routine_id=r.id,
                idempotency_key=f"routine:{r.id}:event:{event.id}",
            )
    except Exception as e:
        print(f"[bots.routines] event handler error: {e}")


def _matches_filter(flt: dict | None, event) -> bool:
    if not flt:
        return True
    details = event.details or {}
    for key, expected in flt.items():
        if details.get(key) != expected:
            return False
    return True


async def ensure_default_routine(user_id: int, bot_id: int | None = None) -> None:
    """Create the morning briefing routine for one user if missing."""
    if not settings.morning_brief_enabled:
        return
    cron = f"{settings.morning_brief_minute} {settings.morning_brief_hour} * * *"

    async with async_session() as db:
        if bot_id is None:
            bot = (
                await db.execute(
                    select(Bot).where(
                        Bot.user_id == user_id,
                        Bot.is_default == True,  # noqa: E712
                        Bot.status == "active",
                    )
                )
            ).scalars().first()
            if bot is None:
                return
            bot_id = bot.id

        existing = (
            await db.execute(
                select(BotRoutine).where(
                    BotRoutine.user_id == user_id,
                    BotRoutine.name == MORNING_ROUTINE,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return

        db.add(
            BotRoutine(
                bot_id=bot_id,
                user_id=user_id,
                name=MORNING_ROUTINE,
                trigger_type="cron",
                cron_expr=cron,
                prompt=(
                    "生成今天的晨间简报。先调用工具获取当前天气、今日日程、"
                    "未完成待办、未读通知和新订阅文章，再用 3-6 句中文口语化地播报："
                    "问候、天气/穿衣建议、今日日程、最重要的 1-2 个待办，"
                    "最后提醒今天最先要做的事。不要 Markdown，不要编造数据。"
                ),
                enabled=True,
                next_run_at=next_run(cron),
            )
        )
        await db.commit()


async def seed_default_routines() -> None:
    """Create the morning briefing routine for every existing user."""
    if not settings.morning_brief_enabled:
        return

    from core.auth.domain.models import User

    async with async_session() as db:
        user_ids = list((await db.execute(select(User.id))).scalars().all())

    for uid in user_ids:
        try:
            await ensure_default_routine(uid)
        except Exception as e:
            print(f"[bots.routines] seed failed for user {uid}: {e}")
