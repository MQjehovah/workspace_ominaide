from datetime import datetime, timedelta

from sqlalchemy import select, update, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from plugins.notifications.backend.models import Notification


def _visible_cond():
    """Snoozed notifications stay hidden until their scheduled time."""
    return or_(Notification.scheduled_at == None, Notification.scheduled_at <= datetime.now())


async def list_notifications(
    db: AsyncSession,
    user_id: int,
    unread: bool = False,
    limit: int = 50,
    type: str | None = None,
) -> list[Notification]:
    q = select(Notification).where(Notification.user_id == user_id, _visible_cond())
    if unread:
        q = q.where(Notification.read == False)
    if type:
        q = q.where(Notification.type == type)
    q = q.order_by(Notification.created_at.desc()).limit(limit)
    r = await db.execute(q)
    return list(r.scalars().all())


async def count_unread(db: AsyncSession, user_id: int) -> int:
    r = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.read == False,
            _visible_cond(),
        )
    )
    return r.scalar() or 0

async def mark_read(db: AsyncSession, user_id: int, notification_id: int) -> bool:
    r = await db.execute(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user_id
        )
    )
    n = r.scalar_one_or_none()
    if not n:
        return False
    n.read = True
    await db.flush()
    return True

async def mark_all_read(db: AsyncSession, user_id: int):
    await db.execute(
        update(Notification).where(
            Notification.user_id == user_id, Notification.read == False
        ).values(read=True)
    )
    await db.flush()

async def create_notification(
    db: AsyncSession,
    user_id: int,
    title: str,
    body: str | None = None,
    type: str = "info",
    link: str | None = None,
    actions: list | None = None,
    dedupe_key: str | None = None,
    scheduled_at: datetime | None = None,
    dedupe_minutes: int | None = 10,
) -> Notification:
    # Collapse repeated reminders for the same event. Pass dedupe_minutes=None
    # for keys that identify a source event permanently (e.g. an email event).
    if dedupe_key:
        query = select(Notification).where(
            Notification.user_id == user_id,
            Notification.dedupe_key == dedupe_key,
        )
        if dedupe_minutes is not None:
            query = query.where(
                Notification.created_at >= datetime.now() - timedelta(minutes=dedupe_minutes)
            )
        existing = (await db.execute(query)).scalar_one_or_none()
        if existing is not None:
            existing._deduped = True
            if dedupe_minutes is not None:
                existing.title = title
                existing.body = body
                existing.type = type
                existing.link = link
                existing.actions = actions
                existing.scheduled_at = scheduled_at
                existing.read = False
            await db.flush()
            await db.refresh(existing)
            return existing

    n = Notification(
        user_id=user_id,
        title=title,
        body=body,
        type=type,
        link=link,
        actions=actions,
        dedupe_key=dedupe_key,
        scheduled_at=scheduled_at,
    )
    n._deduped = False
    db.add(n)
    await db.flush()
    await db.refresh(n)
    return n
