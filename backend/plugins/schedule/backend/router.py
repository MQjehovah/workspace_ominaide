from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from core.database.session import get_db
from core.auth.dependencies import get_current_user
from core.events.recorder import record_event
from core.timeutil import parse_datetime

from plugins.schedule.backend.schemas import EventCreate, EventUpdate, EventResponse
from plugins.schedule.backend import service


router = APIRouter(prefix="/api/schedule", tags=["schedule"])


def _event_details(ev, **extra) -> dict:
    return {
        "event_id": ev.id,
        "title": ev.title,
        "start_time": ev.start_time.isoformat() if ev.start_time else None,
        "end_time": ev.end_time.isoformat() if ev.end_time else None,
        "notes": (ev.notes or "")[:500],
        "color": ev.color,
        "remind_before": ev.remind_before,
        **extra,
    }


@router.get("", response_model=list[EventResponse])
async def list_events(
    start: str | None = Query(None),
    end: str | None = Query(None),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        s = parse_datetime(start) if start else None
        e = parse_datetime(end) if end else None
    except ValueError:
        raise HTTPException(status_code=422, detail="start/end must be ISO datetimes")
    return await service.list_events(db, user["id"], s, e)


@router.post("", response_model=EventResponse, status_code=201)
async def create_event(
    req: EventCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ev = await service.create_event(db, user["id"], req)
    await record_event(db, user["id"], "schedule.created", "schedule", ev.id,
                       f"创建日程: {ev.title}", _event_details(ev))
    return ev


@router.put("/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: int,
    req: EventUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ev = await service.update_event(db, user["id"], event_id, req)
    if not ev:
        raise HTTPException(404, detail="Event not found")
    changes = sorted(req.model_dump(exclude_unset=True).keys())
    await record_event(db, user["id"], "schedule.updated", "schedule", event_id,
                       f"修改日程: {ev.title}",
                       _event_details(ev, changes=changes))
    return ev


@router.delete("/{event_id}")
async def delete_event(
    event_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ev = await service.get_event(db, user["id"], event_id)
    title = ev.title if ev else "未知"
    details = _event_details(ev) if ev else {}
    ok = await service.delete_event(db, user["id"], event_id)
    if not ok:
        raise HTTPException(404, detail="Event not found")
    await record_event(db, user["id"], "schedule.deleted", "schedule", event_id,
                       f"删除日程: {title}", details)
    return {"message": "Deleted"}
