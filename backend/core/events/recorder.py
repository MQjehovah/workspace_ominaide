from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from core.events.models import UserEvent


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
    return event
