"""Automation center API: templates, natural-language rules, dry runs and logs."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.auth.dependencies import get_current_user
from core.bots import automation_service
from core.bots import registry
from core.bots import routines as routine_service
from core.bots.schemas import RoutineOut, RunOut


router = APIRouter(prefix="/api/automation", tags=["automation"])


class ParseRuleRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class FromTemplateRequest(BaseModel):
    bot_id: int
    template_key: str
    overrides: dict | None = None


@router.get("/templates")
async def templates(user: dict = Depends(get_current_user)):
    from core.bots.routine_templates import list_templates

    return {"templates": list_templates()}


@router.post("/parse")
async def parse_rule(req: ParseRuleRequest, user: dict = Depends(get_current_user)):
    try:
        draft = await automation_service.parse_rule(req.text)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"draft": draft}


@router.post("/from-template", response_model=RoutineOut)
async def create_from_template(req: FromTemplateRequest, user: dict = Depends(get_current_user)):
    try:
        await registry.get_active_bot(user["id"], req.bot_id)
    except registry.BotNotFound:
        raise HTTPException(status_code=404, detail="Bot not found")
    try:
        return await automation_service.create_from_template(
            user["id"], req.bot_id, req.template_key, req.overrides
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/routines/{routine_id}")
async def routine_detail(routine_id: int, user: dict = Depends(get_current_user)):
    routine = await routine_service.get_routine(user["id"], routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="Routine not found")
    return RoutineOut.model_validate(routine)


@router.post("/routines/{routine_id}/dry-run")
async def dry_run(routine_id: int, user: dict = Depends(get_current_user)):
    try:
        return await automation_service.dry_run(user["id"], routine_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/routines/{routine_id}/runs")
async def routine_runs(
    routine_id: int,
    limit: int = Query(20, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    routine = await routine_service.get_routine(user["id"], routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="Routine not found")
    return await automation_service.list_routine_runs(user["id"], routine_id, limit)


@router.get("/routines/{routine_id}/stats")
async def routine_stats(
    routine_id: int,
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(get_current_user),
):
    routine = await routine_service.get_routine(user["id"], routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="Routine not found")
    return await automation_service.routine_stats(user["id"], routine_id, days)


@router.get("/overview")
async def overview(user: dict = Depends(get_current_user)):
    return await automation_service.overview(user["id"])
