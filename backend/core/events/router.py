from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from core.events.models import UserActivity

router = APIRouter(prefix="/api/activities", tags=["activities"])


class ActivityResponse(BaseModel):
    id: int
    user_id: int
    event_type: str
    entity_type: str | None = None
    entity_id: int | None = None
    summary: str | None = None
    details: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[ActivityResponse])
async def list_activities(
    limit: int = Query(50, ge=1, le=200),
    event_type: str | None = None,
    entity_type: str | None = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(UserActivity).where(UserActivity.user_id == user["id"])
    if event_type:
        query = query.where(UserActivity.event_type == event_type)
    if entity_type:
        query = query.where(UserActivity.entity_type == entity_type)
    query = query.order_by(desc(UserActivity.created_at)).limit(limit)
    result = await db.execute(query)
    activities = list(result.scalars().all())
    return [ActivityResponse.model_validate(e) for e in activities]
