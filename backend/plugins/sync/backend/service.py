from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from plugins.sync.backend.models import SyncEvent
from plugins.sync.backend.websocket_manager import manager
from core.database.redis import get_redis


async def publish_file_change(
    db: AsyncSession,
    user_id: int,
    workspace_id: int,
    event_type: str,
    file_path: str,
    file_id: int | None = None,
    file_size: int | None = None,
) -> SyncEvent:
    """Record and broadcast a file change event."""
    event = SyncEvent(
        workspace_id=workspace_id,
        user_id=user_id,
        event_type=event_type,
        file_id=file_id,
        file_path=file_path,
        file_size=file_size,
        status="pending",
    )
    db.add(event)
    await db.flush()

    event_data = {
        "id": event.id,
        "workspace_id": workspace_id,
        "event_type": event_type,
        "file_path": file_path,
        "file_id": file_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Push to Redis Stream
    try:
        redis = await get_redis()
        await redis.xadd(f"sync:{workspace_id}", event_data)
    except Exception:
        pass  # Redis not available

    # Broadcast via WebSocket
    await manager.notify_workspace(user_id, workspace_id, event_data)

    return event


async def get_sync_events(
    db: AsyncSession,
    user_id: int,
    workspace_id: int,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[SyncEvent], int]:
    query = select(SyncEvent).where(
        SyncEvent.workspace_id == workspace_id,
        SyncEvent.user_id == user_id,
    ).order_by(SyncEvent.created_at.desc())

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    events = list(result.scalars().all())

    return events, total


async def mark_synced(db: AsyncSession, event_id: int):
    result = await db.execute(select(SyncEvent).where(SyncEvent.id == event_id))
    event = result.scalar_one_or_none()
    if event:
        event.status = "synced"
        await db.flush()


async def mark_conflicted(db: AsyncSession, event_id: int):
    result = await db.execute(select(SyncEvent).where(SyncEvent.id == event_id))
    event = result.scalar_one_or_none()
    if event:
        event.status = "conflicted"
        await db.flush()
