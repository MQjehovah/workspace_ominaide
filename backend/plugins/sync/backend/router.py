from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from plugins.sync.backend.schemas import SyncEventResponse, SyncEventListResponse, SyncFolderResponse, SyncFolderCreate, SyncFolderUpdate, SyncFolderListResponse
from plugins.sync.backend.models import SyncFolder, SyncEvent
from plugins.sync.backend.service import get_sync_events, mark_synced, mark_conflicted

router = APIRouter(prefix="/api/sync", tags=["sync"])

# ---- Sync Folder Management ----

@router.get("/folders", response_model=SyncFolderListResponse)
async def list_sync_folders(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SyncFolder).where(SyncFolder.user_id == user["id"]).order_by(SyncFolder.created_at.desc())
    )
    folders = list(result.scalars().all())
    return SyncFolderListResponse(folders=[SyncFolderResponse.model_validate(f) for f in folders])


@router.post("/folders", response_model=SyncFolderResponse, status_code=201)
async def create_sync_folder(
    req: SyncFolderCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    folder = SyncFolder(
        user_id=user["id"],
        server_path=req.server_path,
        local_path=req.local_path,
    )
    db.add(folder)
    await db.flush()
    await db.refresh(folder)
    return SyncFolderResponse.model_validate(folder)


@router.put("/folders/{folder_id}", response_model=SyncFolderResponse)
async def update_sync_folder(
    folder_id: int,
    req: SyncFolderUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SyncFolder).where(SyncFolder.id == folder_id, SyncFolder.user_id == user["id"])
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Sync folder not found")
    folder.enabled = req.enabled
    await db.flush()
    await db.refresh(folder)
    return SyncFolderResponse.model_validate(folder)


@router.delete("/folders/{folder_id}")
async def delete_sync_folder(
    folder_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SyncFolder).where(SyncFolder.id == folder_id, SyncFolder.user_id == user["id"])
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Sync folder not found")
    await db.delete(folder)
    await db.flush()
    return {"message": "Sync folder deleted"}


# ---- Sync Events ----

@router.get("/events", response_model=SyncEventListResponse)
async def list_sync_events(
    workspace_id: int = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
