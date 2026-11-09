
from core.logging import get_logger
log = get_logger(__name__)
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from datetime import datetime

from core.auth.dependencies import get_current_user
from ai.bots import registry, runner
from ai.bots import routines as routine_service
from ai.bots.memory import add_memory, delete_memory, list_memories
from ai.bots.models import BotApproval, BotRun
from ai.bots.schemas import (
    ApprovalDecision,
    ApprovalOut,
    BotCreate,
    BotOut,
    BotUpdate,
    MemoryCreate,
    MemoryOut,
    AutomationRunOut,
    RoutineCreate,
    RoutineOut,
    RoutineUpdate,
    RunCreate,
    RunDetail,
    RunOut,
    StepOut,
)
from core.database.session import async_session

router = APIRouter(prefix="/api/bots", tags=["bots"])
runs_router = APIRouter(prefix="/api/runs", tags=["runs"])
approvals_router = APIRouter(prefix="/api/approvals", tags=["approvals"])


def _not_found(e: registry.BotNotFound) -> HTTPException:
    return HTTPException(status_code=404, detail="Bot not found")


async def _resolve_bot(user_id: int, bot_id: int):
    try:
        return await registry.get_active_bot(user_id, bot_id)
    except registry.BotNotFound:
        raise HTTPException(status_code=404, detail="Bot not found")


@router.get("", response_model=list[BotOut])
async def list_bots(user: dict = Depends(get_current_user)):
    return await registry.list_bots(user["id"])


@router.post("", response_model=BotOut)
async def create_bot(payload: BotCreate, user: dict = Depends(get_current_user)):
    return await registry.create_bot(user["id"], payload)


@router.get("/{bot_id}", response_model=BotOut)
async def get_bot(bot_id: int, user: dict = Depends(get_current_user)):
    try:
        return await registry.get_active_bot(user["id"], bot_id)
    except registry.BotNotFound:
        raise _not_found(registry.BotNotFound(bot_id))


@router.patch("/{bot_id}", response_model=BotOut)
async def update_bot(
    bot_id: int, payload: BotUpdate, user: dict = Depends(get_current_user)
):
    try:
        return await registry.update_bot(user["id"], bot_id, payload)
    except registry.BotNotFound:
        raise _not_found(registry.BotNotFound(bot_id))
    except registry.BotConflict as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/{bot_id}")
async def delete_bot(
    bot_id: int,
    purge: bool = Query(False),
    user: dict = Depends(get_current_user),
):
    try:
        await registry.delete_bot(user["id"], bot_id, purge=purge)
        return {"message": "Bot deleted" if purge else "Bot archived"}
    except registry.BotNotFound:
        raise _not_found(registry.BotNotFound(bot_id))
    except registry.BotConflict as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{bot_id}/memories", response_model=list[MemoryOut])
async def get_memories(
    bot_id: int,
    kind: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    try:
        await registry.get_active_bot(user["id"], bot_id)
    except registry.BotNotFound:
        raise _not_found(registry.BotNotFound(bot_id))
    return await list_memories(user["id"], bot_id, limit=limit, kind=kind)


@router.post("/{bot_id}/memories", response_model=MemoryOut)
async def create_memory(
    bot_id: int, payload: MemoryCreate, user: dict = Depends(get_current_user)
):
    try:
        await registry.get_active_bot(user["id"], bot_id)
    except registry.BotNotFound:
        raise _not_found(registry.BotNotFound(bot_id))

    try:
        return await add_memory(
            user["id"],
            bot_id,
            payload.content,
            kind=payload.kind,
            importance=payload.importance,
            expires_at=payload.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/{bot_id}/memories/{memory_id}")
async def remove_memory(
    bot_id: int, memory_id: int, user: dict = Depends(get_current_user)
):
    try:
        await registry.get_active_bot(user["id"], bot_id)
    except registry.BotNotFound:
        raise _not_found(registry.BotNotFound(bot_id))

    ok = await delete_memory(user["id"], bot_id, memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"message": "Memory deleted"}


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

@router.post("/{bot_id}/runs", response_model=RunOut, status_code=202)
async def create_bot_run(
    bot_id: int, payload: RunCreate, user: dict = Depends(get_current_user)
):
    bot = await _resolve_bot(user["id"], bot_id)
    run = await runner.create_run(
        user["id"],
        bot,
        payload.prompt,
        trigger="api",
        session_id=payload.session_id,
        auto_start=payload.auto_start,
    )
    return run


@router.get("/{bot_id}/runs", response_model=list[RunOut])
async def list_bot_runs(
    bot_id: int,
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    await _resolve_bot(user["id"], bot_id)
    return await runner.list_runs(user["id"], bot_id, limit)


@runs_router.get("/{run_id}", response_model=RunDetail)
async def get_run_detail(run_id: int, user: dict = Depends(get_current_user)):
    run = await runner.get_run(user["id"], run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    steps = await runner.list_steps(run.id)
    detail = RunDetail.model_validate(run)
    detail.steps = [StepOut.model_validate(s) for s in steps]
    return detail


@runs_router.get("/{run_id}/stream")
async def stream_run(run_id: int, user: dict = Depends(get_current_user)):
    run = await runner.get_run(user["id"], run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return StreamingResponse(
        runner.stream_run(run.id, user["id"]),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@runs_router.post("/{run_id}/cancel")
async def cancel_run(run_id: int, user: dict = Depends(get_current_user)):
    ok = await runner.cancel_run(user["id"], run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"message": "Run cancelled"}


# ---------------------------------------------------------------------------
# Routines
# ---------------------------------------------------------------------------

@router.get("/{bot_id}/routines", response_model=list[RoutineOut])
async def list_bot_routines(bot_id: int, user: dict = Depends(get_current_user)):
    await _resolve_bot(user["id"], bot_id)
    return await routine_service.list_routines(user["id"], bot_id)


@router.post("/{bot_id}/routines", response_model=RoutineOut)
async def create_bot_routine(
    bot_id: int, payload: RoutineCreate, user: dict = Depends(get_current_user)
):
    await _resolve_bot(user["id"], bot_id)
    try:
        return await routine_service.create_routine(
            user["id"],
            bot_id,
            payload.name,
            trigger_type=payload.trigger_type,
            cron_expr=payload.cron_expr,
            event_type=payload.event_type,
            event_filter=payload.event_filter,
            prompt=payload.prompt,
            enabled=payload.enabled,
            spec=payload.spec,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.patch("/{bot_id}/routines/{routine_id}", response_model=RoutineOut)
async def update_bot_routine(
    bot_id: int,
    routine_id: int,
    payload: RoutineUpdate,
    user: dict = Depends(get_current_user),
):
    await _resolve_bot(user["id"], bot_id)
    try:
        routine = await routine_service.update_routine(
            user["id"], routine_id, payload.model_dump(exclude_unset=True)
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if routine is None or routine.bot_id != bot_id:
        raise HTTPException(status_code=404, detail="Routine not found")
    return routine


@router.delete("/{bot_id}/routines/{routine_id}")
async def delete_bot_routine(
    bot_id: int, routine_id: int, user: dict = Depends(get_current_user)
):
    await _resolve_bot(user["id"], bot_id)
    routine = await routine_service.get_routine(user["id"], routine_id)
    if routine is None or routine.bot_id != bot_id:
        raise HTTPException(status_code=404, detail="Routine not found")
    ok = await routine_service.delete_routine(user["id"], routine_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Routine not found")
    return {"message": "Routine deleted"}


@router.post("/{bot_id}/routines/{routine_id}/run", status_code=202)
async def run_bot_routine(
    bot_id: int,
    routine_id: int,
    force: bool = Query(False),
    user: dict = Depends(get_current_user),
):
    await _resolve_bot(user["id"], bot_id)
    routine = await routine_service.get_routine(user["id"], routine_id)
    if routine is None or routine.bot_id != bot_id:
        raise HTTPException(status_code=404, detail="Routine not found")
    result = await routine_service.run_routine_now(user["id"], routine_id, force=force)
    if result is None:
        raise HTTPException(status_code=422, detail="Routine could not be run")
    return result


@router.get("/{bot_id}/routines/{routine_id}/runs", response_model=list[AutomationRunOut])
async def list_bot_routine_runs(
    bot_id: int,
    routine_id: int,
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    await _resolve_bot(user["id"], bot_id)
    routine = await routine_service.get_routine(user["id"], routine_id)
    if routine is None or routine.bot_id != bot_id:
        raise HTTPException(status_code=404, detail="Routine not found")
    return await routine_service.list_routine_runs(user["id"], routine_id, limit)


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------

@approvals_router.get("", response_model=list[ApprovalOut])
async def list_approvals(
    status: str = Query("pending"),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    async with async_session() as db:
        q = select(BotApproval).where(BotApproval.user_id == user["id"])
        if status and status != "all":
            q = q.where(BotApproval.status == status)
        q = q.order_by(BotApproval.id.desc()).limit(limit)
        return list((await db.execute(q)).scalars().all())


@approvals_router.post("/{approval_id}/decision", response_model=ApprovalOut)
async def decide_approval(
    approval_id: int,
    payload: ApprovalDecision,
    user: dict = Depends(get_current_user),
):
    run_id = None
    async with async_session() as db:
        approval = (
            await db.execute(
                select(BotApproval).where(
                    BotApproval.id == approval_id,
                    BotApproval.user_id == user["id"],
                )
            )
        ).scalar_one_or_none()
        if approval is None:
            raise HTTPException(status_code=404, detail="Approval not found")
        if approval.status != "pending":
            raise HTTPException(status_code=409, detail="Approval already decided")

        approval.status = "approved" if payload.approved else "denied"
        approval.reason = payload.reason
        approval.decided_at = datetime.utcnow()

        if payload.approved and payload.remember:
            from datetime import timedelta

            from ai.cognition.models import CapabilityGrant

            scope = payload.scope if payload.scope in ("once", "goal", "session", "day", "always") else "always"
            expires_at = None
            if scope == "once":
                expires_at = datetime.utcnow() + timedelta(minutes=5)
            elif scope == "day":
                expires_at = datetime.utcnow() + timedelta(days=1)
            db.add(CapabilityGrant(
                user_id=user["id"],
                bot_id=approval.bot_id,
                capability_key=(approval.capability_key or approval.tool_name)[:160],
                decision="allow",
                scope=scope,
                constraints={"approval_id": approval.id},
                expires_at=expires_at,
            ))

        run = (
            await db.execute(select(BotRun).where(BotRun.id == approval.run_id))
        ).scalar_one_or_none()
        if run is not None and run.status in ("waiting_approval", "queued"):
            run.status = "queued"
            run_id = run.id

        try:
            from core.events.bus import record_event
            from activities.preview import preview_arguments

            approved = bool(payload.approved)
            await record_event(
                db, user["id"], "approval.decided", "approval", approval.id,
                f"{'批准' if approved else '拒绝'}工具调用：{approval.tool_name}",
                {
                    "approval_id": approval.id,
                    "run_id": approval.run_id,
                    "bot_id": approval.bot_id,
                    "tool_name": approval.tool_name,
                    "risk_level": approval.risk_level,
                    "approved": approved,
                    "remember": bool(payload.remember),
                    "reason": payload.reason,
                    "arguments_preview": preview_arguments(approval.arguments),
                },
            )
        except Exception as e:
            log.warning(f"[approvals] activity record failed: {e}")

        await db.commit()
        await db.refresh(approval)

    if run_id is not None:
        runner.enqueue_run(run_id)
    return approval
