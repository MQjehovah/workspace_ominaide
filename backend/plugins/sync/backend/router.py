from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from plugins.sync.backend.schemas import SyncEventResponse, SyncEventListResponse
from plugins.sync.backend.service import get_sync_events, mark_synced, mark_conflicted
from plugins.workspaces.backend.service import get_workspace

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.get("/events", response_model=SyncEventListResponse)
async def list_sync_events(
    workspace_id: int = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify workspace access
    ws = await get_workspace(db, user["id"], workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    events, total = await get_sync_events(db, user["id"], workspace_id, page, page_size)
    return SyncEventListResponse(
        events=[SyncEventResponse.model_validate(e) for e in events],
        total=total,
    )


@router.post("/events/{event_id}/synced")
async def confirm_synced(
    event_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await mark_synced(db, event_id)
    return {"message": "Event marked as synced"}


@router.post("/events/{event_id}/conflicted")
async def report_conflict(
    event_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await mark_conflicted(db, event_id)
    return {"message": "Event marked as conflicted"}
