from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from plugins.notifications.backend.models import Notification

async def list_notifications(db: AsyncSession, user_id: int, unread: bool = False, limit: int = 50) -> list[Notification]:
    q = select(Notification).where(Notification.user_id == user_id)
    if unread:
        q = q.where(Notification.read == False)
    q = q.order_by(Notification.created_at.desc()).limit(limit)
    r = await db.execute(q)
    return list(r.scalars().all())

async def count_unread(db: AsyncSession, user_id: int) -> int:
    r = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id, Notification.read == False
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
    db: AsyncSession, user_id: int, title: str,
    body: str | None = None, type: str = "info", link: str | None = None
) -> Notification:
    n = Notification(user_id=user_id, title=title, body=body, type=type, link=link)
    db.add(n)
    await db.flush()
    await db.refresh(n)
    return n
