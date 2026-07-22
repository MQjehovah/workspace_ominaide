"""Event bus — fire-and-forget event emission + background worker processing.

Business modules call record_event() to emit events. The recorder writes
to DB and pushes to Redis queue. A background worker pops events and
calls registered handlers (indexing, entity extraction, etc.).
"""
import asyncio
import json
from typing import Callable, Awaitable
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import async_session
from core.events.models import UserActivity as UserEvent

EventHandler = Callable[[UserEvent], Awaitable[None]]
_handlers: list[EventHandler] = []


def subscribe(handler: EventHandler):
    _handlers.append(handler)


async def record_event(
    db: AsyncSession,
    user_id: int,
    event_type: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    summary: str | None = None,
    details: dict | None = None,
) -> UserEvent:
    event = UserEvent(
        user_id=user_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        details=details,
    )
    db.add(event)
    await db.flush()

    # Push to Redis queue for async processing
    try:
        from core.database.redis import get_redis
        redis = await get_redis()
        await redis.rpush("event_queue", json.dumps({
            "event_id": event.id,
            "user_id": user_id,
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
        }, ensure_ascii=False))
    except Exception as e:
        print(f"[bus] redis push error: {e}")

    return event


async def _process_event(payload: dict):
    event_id = payload.get("event_id")
    if not event_id:
        return
    async with async_session() as db:
        from sqlalchemy import select
        r = await db.execute(select(UserEvent).where(UserEvent.id == event_id))
        event = r.scalar_one_or_none()
        if not event:
            return
        for handler in _handlers:
            try:
                await handler(event)
            except Exception as e:
                print(f"[bus] handler error: {e}")


async def worker_loop():
    """Background worker: poll Redis queue and process events."""
    while True:
        try:
            from core.database.redis import get_redis
            redis = await get_redis()
            _, raw = await redis.blpop("event_queue", timeout=30)
            if raw:
                payload = json.loads(raw)
                asyncio.create_task(_process_event(payload))
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            print(f"[bus] worker error: {e}")
            await asyncio.sleep(5)
