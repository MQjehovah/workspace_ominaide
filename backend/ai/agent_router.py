from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.auth.dependencies import get_current_user
from ai.bots import registry, runner
from ai.bots.schemas import RunDetail, RunOut, StepOut

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentTaskCreate(BaseModel):
    goal: str = Field(min_length=1, max_length=20000)
    bot_id: int | None = None
    idempotency_key: str | None = Field(default=None, max_length=160)


@router.post("/tasks", response_model=RunOut, status_code=202)
async def create_agent_task(
    req: AgentTaskCreate,
    user: dict = Depends(get_current_user),
):
    try:
        bot = await registry.get_active_bot(user["id"], req.bot_id)
    except registry.BotNotFound:
        raise HTTPException(status_code=404, detail="Bot not found")
    return await runner.create_run(
        user["id"],
        bot,
        req.goal,
        trigger="agent",
        idempotency_key=req.idempotency_key,
    )


@router.get("/tasks", response_model=list[RunOut])
async def list_agent_tasks(
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    runs = await runner.list_runs(user["id"], limit=limit)
    return [run for run in runs if run.trigger == "agent"]


@router.get("/tasks/{run_id}", response_model=RunDetail)
async def get_agent_task(
    run_id: int,
    user: dict = Depends(get_current_user),
):
    run = await runner.get_run(user["id"], run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Task not found")
    steps = await runner.list_steps(run.id)
    detail = RunDetail.model_validate(run)
    detail.steps = [StepOut.model_validate(step) for step in steps]
    return detail


@router.post("/tasks/{run_id}/cancel")
async def cancel_agent_task(
    run_id: int,
    user: dict = Depends(get_current_user),
):
    ok = await runner.cancel_run(user["id"], run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Cancelled"}
