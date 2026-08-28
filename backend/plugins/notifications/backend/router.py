from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from plugins.notifications.backend.schemas import NotificationResponse
from plugins.notifications.backend import service

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


async def notify_user(user_id: int, data: dict):
    """Push a notification to every client of the user over the shared
    host channel (`channel: "notifications"`)."""
    from core.wschannel.hub import host_channel
    await host_channel.broadcast(user_id, "notifications", data)


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    unread: bool = False, limit: int = 50,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_notifications(db, user["id"], unread, limit)


@router.get("/unread-count")
async def unread_count(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return {"count": await service.count_unread(db, user["id"])}


@router.put("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await service.mark_read(db, user["id"], notification_id)
    if not ok:
        raise HTTPException(404, detail="Not found")
    return {"message": "Read"}


@router.put("/read-all")
async def mark_all_read(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await service.mark_all_read(db, user["id"])
    return {"message": "All read"}
