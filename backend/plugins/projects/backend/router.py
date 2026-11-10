from fastapi import APIRouter, Depends, HTTPException, Query

from core.auth.dependencies import get_current_user
from ai.bots.registry import get_or_create_default_bot
from ai.bots.schemas import RunOut
from ai.coding.service import create_coding_run
from plugins.projects.backend import service
from plugins.projects.backend.schemas import (
    ProjectCreate,
    ProjectOut,
    ProjectRunCreate,
    ProjectRunOut,
    ProjectUpdate,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
async def list_projects(user: dict = Depends(get_current_user)):
    return await service.list_projects(user["id"])


@router.post("", response_model=ProjectOut)
async def create_project(payload: ProjectCreate, user: dict = Depends(get_current_user)):
    try:
        return await service.create_project(user["id"], payload)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/{project_id}")
async def delete_project(project_id: int, user: dict = Depends(get_current_user)):
    try:
        ok = await service.delete_project(user["id"], project_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"message": "Project and directory deleted"}


@router.get("/runs", response_model=list[ProjectRunOut])
async def list_coding_runs(
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    return await service.list_all_coding_runs(user["id"], limit)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, user: dict = Depends(get_current_user)):
    project = await service.get_project(user["id"], project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: int, payload: ProjectUpdate, user: dict = Depends(get_current_user)
):
    try:
        project = await service.update_project(user["id"], project_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}/runs", response_model=list[ProjectRunOut])
async def list_project_runs(
    project_id: int,
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    project = await service.get_project(user["id"], project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return await service.list_project_runs(user["id"], project.path, limit)


@router.post("/{project_id}/runs", response_model=RunOut, status_code=202)
async def start_project_run(
    project_id: int,
    payload: ProjectRunCreate,
    user: dict = Depends(get_current_user),
):
    project = await service.get_project(user["id"], project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    bot = await get_or_create_default_bot(user["id"])
    return await create_coding_run(
        user["id"],
        bot,
        project.path,
        payload.instruction,
        branch=payload.branch,
        engine=payload.engine,
    )
