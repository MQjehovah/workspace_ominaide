"""Bot routines: cron schedules and event triggers.

The loop runs in the FastAPI lifespan alongside the existing system scheduler.
Cron expressions are the standard 5-field form (minute hour dom month dow).
"""

from core.logging import get_logger
log = get_logger(__name__)
import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select, delete, update

from ai.automation.dsl import compile_spec, spec_from_routine, spec_legacy_fields
from ai.bots import runner
from ai.bots.models import Bot, BotRoutine
from core.database.session import async_session


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
                         enabled: bool = True, spec: dict | None = None) -> BotRoutine:
    if spec:
        spec = dict(spec)
        spec.setdefault("name", name)
        spec.setdefault("enabled", enabled)
        raw = {"spec": spec}
    else:
        raw = {
            "name": name,
            "trigger_type": trigger_type,
            "cron_expr": cron_expr,
            "event_type": event_type,
            "event_filter": event_filter,
            "prompt": prompt,
            "enabled": enabled,
        }
    compiled = compile_spec(raw)
    if not compiled.get("valid"):
        raise ValueError(str(compiled.get("errors")))
    normalized = compiled["spec"]
    normalized["name"] = (name or normalized.get("name") or "routine")[:120]
    normalized["enabled"] = bool(enabled)
    legacy = spec_legacy_fields(normalized)

    nxt = None
    if normalized["trigger"].get("type") == "schedule":
        nxt = next_run(normalized["trigger"]["cron"])

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
            name=normalized["name"],
            trigger_type=legacy["trigger_type"],
            cron_expr=legacy["cron_expr"],
            event_type=legacy["event_type"],
            event_filter=event_filter,
            prompt=legacy["prompt"],
            enabled=normalized["enabled"],
            next_run_at=nxt,
            spec=normalized,
            spec_version=1,
            run_count=0,
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

        current = spec_from_routine(routine)
        if isinstance(data.get("spec"), dict):
            spec = dict(data["spec"])
            spec.setdefault("name", data.get("name") or routine.name)
            raw = {"spec": spec}
        elif any(k in data for k in ("trigger_type", "cron_expr", "event_type", "prompt")):
            raw = {
                "name": data.get("name") or current.get("name") or routine.name,
                "trigger_type": data.get("trigger_type", routine.trigger_type),
                "cron_expr": data.get("cron_expr", routine.cron_expr),
                "event_type": data.get("event_type", routine.event_type),
                "prompt": data.get("prompt", routine.prompt),
                "enabled": data.get("enabled", routine.enabled),
            }
        else:
            raw = {"spec": current}
            raw["spec"]["name"] = data.get("name") or current.get("name") or routine.name
            raw["spec"]["enabled"] = bool(data.get("enabled", routine.enabled))

        compiled = compile_spec(raw)
        if not compiled.get("valid"):
            raise ValueError(str(compiled.get("errors")))
        normalized = compiled["spec"]
        normalized["name"] = str(data.get("name") or normalized.get("name") or routine.name)[:120]
        normalized["enabled"] = bool(data.get("enabled", normalized.get("enabled", True)))
        legacy = spec_legacy_fields(normalized)

        routine.name = normalized["name"]
        routine.trigger_type = legacy["trigger_type"]
        routine.cron_expr = legacy["cron_expr"]
        routine.event_type = legacy["event_type"]
        routine.prompt = legacy["prompt"]
        if "event_filter" in data:
            routine.event_filter = data["event_filter"]
        routine.enabled = normalized["enabled"]
        routine.spec = normalized
        routine.spec_version = 1

        if normalized["trigger"].get("type") == "schedule":
            routine.next_run_at = next_run(normalized["trigger"]["cron"])
        else:
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


async def run_routine_now(user_id: int, routine_id: int, *, force: bool = False):
    routine = await get_routine(user_id, routine_id)
    if routine is None:
        return None
    from ai.automation.executor import execute_automation

    return await execute_automation(
        routine.id, "manual", manual={"user_id": user_id}, force=force,
    )


async def list_routine_runs(user_id: int, routine_id: int, limit: int = 50):
    from ai.automation.models import AutomationRun

    async with async_session() as db:
        rows = list((await db.execute(
            select(AutomationRun).where(
                AutomationRun.user_id == user_id,
                AutomationRun.routine_id == routine_id,
            ).order_by(AutomationRun.id.desc()).limit(min(max(limit, 1), 200))
        )).scalars().all())
    return rows


async def routine_loop() -> None:
    """Every 30s, fire due cron routines."""
    while True:
        try:
            await _tick()
        except Exception as e:
            log.warning(f"[bots.routines] loop error: {e}")
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
            from ai.automation.executor import execute_automation

            result = await execute_automation(
                r.id, "schedule", scheduled_for=now,
            )
            await _mark_tick(
                r.id, next_run(r.cron_expr, now),
                "skipped" if result.get("status") == "skipped" else "queued",
            )
        except Exception as e:
            log.warning(f"[bots.routines] tick {r.id} failed: {e}")
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
            async with async_session() as db:
                bot = (
                    await db.execute(select(Bot).where(Bot.id == r.bot_id))
                ).scalar_one_or_none()
            if bot is None or bot.status != "active":
                continue
            from ai.automation.executor import execute_automation

            await execute_automation(r.id, "event", event=event)
    except Exception as e:
        log.warning(f"[bots.routines] event handler error: {e}")


def _event_context(event) -> str:
    """Give event-triggered routines the payload, not just a generic prompt."""
    import json

    parts: list[str] = []
    if event.summary:
        parts.append(f"事件摘要: {event.summary}")
    if event.details:
        try:
            parts.append("事件详情: " + json.dumps(event.details, ensure_ascii=False)[:8000])
        except Exception:
            pass
    return "\n".join(parts)


def _matches_filter(flt: dict | None, event) -> bool:
    if not flt:
        return True
    details = event.details or {}
    for key, expected in flt.items():
        if details.get(key) != expected:
            return False
    return True



