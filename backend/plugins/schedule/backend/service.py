import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from core.ai.indexer import index_content
from plugins.schedule.backend.models import Event
from plugins.schedule.backend.schemas import EventCreate, EventUpdate


async def list_events(
    db: AsyncSession, user_id: int, start: datetime | None = None, end: datetime | None = None
) -> list[Event]:
    q = select(Event).where(Event.user_id == user_id)
    if start:
        q = q.where(Event.start_time >= start)
    if end:
        q = q.where(Event.start_time <= end)
    q = q.order_by(Event.start_time)
    r = await db.execute(q)
    return list(r.scalars().all())


async def create_event(db: AsyncSession, user_id: int, req: EventCreate) -> Event:
    ev = Event(user_id=user_id, **req.model_dump())
    db.add(ev)
    await db.flush()
    await db.refresh(ev)

    asyncio.create_task(index_content(
        user_id=user_id,
        source_type='event',
        source_id=ev.id,
        title=ev.title,
        content=ev.notes or '',
        metadata={"link": f"/schedule/events/{ev.id}"},
    ))

    return ev


async def get_event(db: AsyncSession, user_id: int, event_id: int) -> Event | None:
    r = await db.execute(select(Event).where(Event.id == event_id, Event.user_id == user_id))
    return r.scalar_one_or_none()


async def update_event(
    db: AsyncSession, user_id: int, event_id: int, req: EventUpdate
) -> Event | None:
    ev = await get_event(db, user_id, event_id)
    if not ev:
        return None
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(ev, k, v)
    await db.flush()
    await db.refresh(ev)

    asyncio.create_task(index_content(
        user_id=user_id,
        source_type='event',
        source_id=ev.id,
        title=ev.title,
        content=ev.notes or '',
        metadata={"link": f"/schedule/events/{ev.id}"},
    ))

    return ev


async def delete_event(db: AsyncSession, user_id: int, event_id: int) -> bool:
    ev = await get_event(db, user_id, event_id)
    if not ev:
        return False
    await db.delete(ev)
    await db.flush()
    return True
