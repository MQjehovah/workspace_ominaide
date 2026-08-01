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


@router.get("/stats")
async def activity_stats(
    days: int = Query(7, ge=1, le=90),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated activity stats for the activity-management page."""
    from datetime import datetime, timedelta
    since = datetime.utcnow() - timedelta(days=days)

    # App usage: sum minutes per app (from app.used events).
    r = await db.execute(
        select(UserActivity).where(
            UserActivity.user_id == user["id"],
            UserActivity.event_type == "app.used",
            UserActivity.created_at >= since,
        )
    )
    app_minutes: dict[str, int] = {}
    for e in r.scalars().all():
        d = e.details or {}
        app = d.get("app") or "未知"
        app_minutes[app] = app_minutes.get(app, 0) + int(d.get("minutes") or 0)

    # Event type distribution.
    r2 = await db.execute(
        select(UserActivity.event_type, func.count())
        .where(UserActivity.user_id == user["id"], UserActivity.created_at >= since)
        .group_by(UserActivity.event_type)
    )
    type_counts = {t: c for t, c in r2.all()}

    top_apps = sorted(
        ({"app": k, "minutes": v} for k, v in app_minutes.items()),
        key=lambda x: -x["minutes"],
    )
    return {
        "days": days,
        "app_minutes": top_apps[:10],
        "total_minutes": sum(app_minutes.values()),
        "top_app": top_apps[0]["app"] if top_apps else None,
        "type_counts": type_counts,
        "clipboard_count": type_counts.get("clipboard.copy", 0),
        "event_count": sum(type_counts.values()),
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
