from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from datetime import datetime

from plugins.files.backend.sync_schemas import (
    SyncEventResponse,
    SyncEventListResponse,
    SyncFolderResponse,
    SyncFolderCreate,
    SyncFolderUpdate,
    SyncFolderListResponse,
    SyncSettingListResponse,
    SyncSettingResponse,
    SyncSettingUpdate,
)
from plugins.files.backend.sync_models import SyncFolder, SyncEvent, SyncSetting
from plugins.files.backend.sync_service import get_sync_events, mark_synced, mark_conflicted

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
    sync_folder_id: int = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    events, total = await get_sync_events(db, user["id"], sync_folder_id, page, page_size)
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
    await mark_synced(db, user["id"], event_id)
    await db.commit()
    return {"message": "Event marked as synced"}


@router.post("/events/{event_id}/conflicted")
async def report_conflict(
    event_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await mark_conflicted(db, user["id"], event_id)
    await db.commit()
    return {"message": "Event marked as conflicted"}


# ---- Cross-device settings ----

@router.get("/settings/{namespace}", response_model=SyncSettingListResponse)
async def list_sync_settings(
    namespace: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(SyncSetting).where(
            SyncSetting.user_id == user["id"],
            SyncSetting.namespace == namespace,
        )
    )).scalars().all()
    return SyncSettingListResponse(
        items=[SyncSettingResponse.model_validate(r) for r in rows]
    )


@router.put("/settings/{namespace}/{key}", response_model=SyncSettingResponse)
async def put_sync_setting(
    namespace: str,
    key: str,
    req: SyncSettingUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(
        select(SyncSetting).where(
            SyncSetting.user_id == user["id"],
            SyncSetting.namespace == namespace,
            SyncSetting.key == key,
        )
    )).scalar_one_or_none()
    if row is None:
        row = SyncSetting(
            user_id=user["id"],
            namespace=namespace,
            key=key,
        )
        db.add(row)
    row.value = req.value
    row.device_id = req.device_id
    row.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(row)
    return SyncSettingResponse.model_validate(row)
