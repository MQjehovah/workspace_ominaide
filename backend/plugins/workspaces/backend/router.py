from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from plugins.workspaces.backend.schemas import (
    WorkspaceCreate, WorkspaceUpdate, WorkspaceResponse,
)
from plugins.workspaces.backend import service as workspace_service
from plugins.files.backend.service import get_files
from plugins.files.backend.schemas import FileQueryParams, FileResponse, FileListResponse

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    req: WorkspaceCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace = await workspace_service.create_workspace(db, user["id"], req)
    return WorkspaceResponse.model_validate(workspace)


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspaces = await workspace_service.get_workspaces(db, user["id"])
    return [WorkspaceResponse.model_validate(w) for w in workspaces]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace = await workspace_service.get_workspace(db, user["id"], workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return WorkspaceResponse.model_validate(workspace)


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: int,
    req: WorkspaceUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        workspace = await workspace_service.update_workspace(
            db, user["id"], workspace_id, req
        )
        return WorkspaceResponse.model_validate(workspace)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await workspace_service.delete_workspace(db, user["id"], workspace_id)
        return {"message": "Workspace deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{workspace_id}/files", response_model=FileListResponse)
async def list_workspace_files(
    workspace_id: int,
    page: int = 1,
    page_size: int = 50,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace = await workspace_service.get_workspace(db, user["id"], workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    params = FileQueryParams(
        page=page, page_size=page_size,
        workspace_id=workspace_id,
    )
    files, total = await get_files(db, user["id"], params)
    return FileListResponse(
        files=[FileResponse.model_validate(f) for f in files],
        total=total, page=page, page_size=page_size,
    )
