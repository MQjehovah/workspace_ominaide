from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from plugins.notifications.backend.schemas import (
    NotificationActionRequest,
    NotificationResponse,
)
from plugins.notifications.backend.models import Notification
from plugins.notifications.backend import service

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


async def notify_user(user_id: int, data: dict):
    """Push a notification to every client of the user.

    - desktop / web / mobile: shared host channel (`channel: "notifications"`)
    - hardware devices: device long-poll bus (low-latency, battery friendly)
    """
    from core.wschannel.hub import host_channel
    await host_channel.broadcast(user_id, "notifications", data)
    try:
        from plugins.device.backend.events import publish_device_event
        await publish_device_event(user_id, "notification", data)
    except Exception:
        pass


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    unread: bool = False, limit: int = 50, type: str | None = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_notifications(db, user["id"], unread, limit, type)


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


@router.post("/{notification_id}/action")
async def act_on_notification(
    notification_id: int,
    req: NotificationActionRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute an inline action (complete todo / snooze / open)."""
    n = (await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user["id"],
        )
    )).scalar_one_or_none()
    if n is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    action = next(
        (
            a for a in (n.actions or [])
            if isinstance(a, dict) and (
                a.get("key") == req.action or a.get("kind") == req.action
            )
        ),
        None,
    )
    if action is None:
        raise HTTPException(status_code=400, detail="Unknown action")

    kind = action.get("kind") or action.get("key")
    link = action.get("link") or n.link

    if kind == "complete_todo":
        from plugins.todo.backend import service as todo_service
        from plugins.todo.backend.schemas import TodoUpdate
        from core.events.recorder import record_event

        todo_id = int(action.get("todo_id") or 0)
        todo = await todo_service.get_todo(db, user["id"], todo_id) if todo_id else None
        if todo is None:
            raise HTTPException(status_code=404, detail="Todo not found")
        await todo_service.update_todo(db, user["id"], todo_id, TodoUpdate(status="done"))
        await record_event(
            db, user["id"], "todo.completed", "todo", todo_id,
            f"从通知完成待办: {todo.title}",
        )
        n.read = True
        await db.flush()
        return {"message": "Todo completed", "todo_id": todo_id}

    if kind == "snooze":
        minutes = max(1, min(int(action.get("minutes") or 10), 24 * 60))
        n.scheduled_at = datetime.now() + timedelta(minutes=minutes)
        n.read = False
        await db.flush()
        return {"message": "Snoozed", "scheduled_at": n.scheduled_at.isoformat()}

    # open (and any unknown-but-present action) behaves as "view".
    n.read = True
    await db.flush()
    return {"message": "Opened", "link": link}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(
        sql_delete(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user["id"],
        )
    )
    if not r.rowcount:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"message": "Deleted"}
