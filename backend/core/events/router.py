from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from core.events.models import UserEvent

router = APIRouter(prefix="/api/events", tags=["events"])


class EventResponse(BaseModel):
    id: int
    user_id: int
    event_type: str
    entity_type: str | None = None
    entity_id: int | None = None
    summary: str | None = None
    details: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[EventResponse])
async def list_events(
    limit: int = Query(50, ge=1, le=200),
    event_type: str | None = None,
    entity_type: str | None = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(UserEvent).where(UserEvent.user_id == user["id"])
    if event_type:
        query = query.where(UserEvent.event_type == event_type)
    if entity_type:
        query = query.where(UserEvent.entity_type == entity_type)
    query = query.order_by(desc(UserEvent.created_at)).limit(limit)
    result = await db.execute(query)
    events = list(result.scalars().all())
    return [EventResponse.model_validate(e) for e in events]
