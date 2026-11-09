from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from activities.models import UserActivity

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


class ActivityCreate(BaseModel):
    event_type: str
    entity_type: str | None = None
    entity_id: int | None = None
    summary: str | None = None
    details: dict | None = None


@router.get("", response_model=list[ActivityResponse])
async def list_activities(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    event_type: str | None = None,
    entity_type: str | None = None,
    days: int | None = Query(None, ge=1, le=90),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timedelta
    query = select(UserActivity).where(UserActivity.user_id == user["id"])
    if event_type:
        query = query.where(UserActivity.event_type == event_type)
    if entity_type:
        query = query.where(UserActivity.entity_type == entity_type)
    if days:
        query = query.where(UserActivity.created_at >= (datetime.utcnow() - timedelta(days=days)))
    query = query.order_by(desc(UserActivity.created_at)).offset(offset).limit(limit)
    result = await db.execute(query)
    activities = list(result.scalars().all())
    return [ActivityResponse.model_validate(e) for e in activities]


@router.get("/page")
async def page_activities(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    event_type: str | None = None,
    entity_type: str | None = None,
    days: int | None = Query(None, ge=1, le=90),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timedelta
    query = select(UserActivity).where(UserActivity.user_id == user["id"])
    if event_type:
        query = query.where(UserActivity.event_type == event_type)
    if entity_type:
        query = query.where(UserActivity.entity_type == entity_type)
    if days:
        query = query.where(UserActivity.created_at >= (datetime.utcnow() - timedelta(days=days)))
    total = (await db.execute(
        select(func.count()).select_from(query.subquery())
    )).scalar() or 0
    rows = list((await db.execute(
        query.order_by(desc(UserActivity.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all())
    return {
        "items": [ActivityResponse.model_validate(row) for row in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@router.get("/stats")
async def activity_stats(
    days: int = Query(7, ge=1, le=90),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated activity stats for the activity-management page."""
    from datetime import datetime, timedelta
    since = datetime.utcnow() - timedelta(days=days)

    # Event type distribution.
    r2 = await db.execute(
        select(UserActivity.event_type, func.count())
        .where(UserActivity.user_id == user["id"], UserActivity.created_at >= since)
        .group_by(UserActivity.event_type)
    )
    type_counts = {t: c for t, c in r2.all()}

    return {
        "days": days,
        "type_counts": type_counts,
        "event_count": sum(type_counts.values()),
        "type_count": len(type_counts),
    }


@router.post("", response_model=ActivityResponse, status_code=201)
async def record_activity(
    req: ActivityCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a client-reported activity event (e.g. desktop app usage) into the event stream."""
    from core.events.recorder import record_event
    event = await record_event(
        db, user["id"], req.event_type, req.entity_type, req.entity_id, req.summary, req.details
    )
    await db.refresh(event)
    await db.commit()
    return ActivityResponse.model_validate(event)
