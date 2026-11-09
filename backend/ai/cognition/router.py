from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from core.auth.dependencies import get_current_user
from ai.cognition import authorization
from ai.cognition.capabilities import capability_dict, list_capabilities
from ai.cognition.proposals import act_proposal, get_proposal, list_proposals
from ai.cognition import goals as goal_service
from ai.cognition import orchestrator, planner
from ai.cognition.agent_profiles import PROFILES
from ai.cognition.dispatcher import dispatch_goal
from ai.cognition.verifier import verify_task
from ai.cognition.schemas import (
    CapabilityOut,
    GoalCreate,
    GoalOut,
    GrantCreate,
    GrantOut,
    HandoffRequest,
    ProposalAct,
    ProposalOut,
    TaskCreate,
    TaskOut,
    TaskUpdate,
    WorkspaceArtifactCreate,
    WorkspaceItemCreate,
)
from ai.cognition import workspace as workspace_service
from ai.cognition.handoff import handoff
from ai.cognition.situation import get_situation

proposals_router = APIRouter(prefix="/api/proposals", tags=["proposals"])
capabilities_router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])
situation_router = APIRouter(prefix="/api/cognition", tags=["cognition"])
goals_router = APIRouter(prefix="/api/cognition/goals", tags=["goals"])
workspaces_router = APIRouter(prefix="/api/cognition/workspaces", tags=["workspaces"])
tasks_router = APIRouter(prefix="/api/cognition/tasks", tags=["tasks"])
agent_profiles_router = APIRouter(prefix="/api/cognition/agent-profiles", tags=["agent-profiles"])


@agent_profiles_router.get("")
async def agent_profiles(user: dict = Depends(get_current_user)):
    return [
        {
            "key": profile.key,
            "title": profile.title,
            "read_only": profile.read_only,
            "max_turns": profile.max_turns,
            "acceptance_hint": profile.acceptance_hint,
        }
        for profile in PROFILES.values()
    ]


@situation_router.get("/now")
async def now(
    refresh: bool = Query(False),
    user: dict = Depends(get_current_user),
):
    return await get_situation(user["id"], force=refresh)


@situation_router.post("/handoff")
async def handoff_to_machine(
    payload: HandoffRequest,
    user: dict = Depends(get_current_user),
):
    return await handoff(
        user["id"],
        machine_id=payload.machine_id,
        goal_id=payload.goal_id,
        session_id=payload.session_id,
        note=payload.note,
    )


@proposals_router.get("", response_model=dict)
async def proposals(
    status: str = Query("new"),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    return {"items": await list_proposals(user["id"], status=status, limit=limit)}


@proposals_router.get("/{proposal_id}", response_model=ProposalOut)
async def proposal_detail(proposal_id: int, user: dict = Depends(get_current_user)):
    row = await get_proposal(user["id"], proposal_id)
    if row is None:
        raise HTTPException(404, detail="Proposal not found")
    return row


@proposals_router.post("/{proposal_id}/act")
async def proposal_act(
    proposal_id: int,
    payload: ProposalAct,
    user: dict = Depends(get_current_user),
):
    result = await act_proposal(
        user["id"],
        proposal_id,
        action=payload.action,
        snooze_minutes=payload.snooze_minutes,
    )
    if result is None:
        raise HTTPException(404, detail="Proposal not found")
    return result


@goals_router.get("", response_model=list[GoalOut])
async def goals(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    return await goal_service.list_goals(user["id"], status=status, limit=limit)


@goals_router.post("", response_model=GoalOut, status_code=201)
async def add_goal(payload: GoalCreate, user: dict = Depends(get_current_user)):
    return await goal_service.create_goal(
        user["id"],
        title=payload.title,
        description=payload.description,
        bot_id=payload.bot_id,
        due_at=payload.due_at,
        priority=payload.priority,
        success_criteria=payload.success_criteria,
        context=payload.context,
        primary_session_id=payload.primary_session_id,
        origin_message_id=payload.origin_message_id,
    )


@goals_router.get("/{goal_id}", response_model=GoalOut)
async def goal_detail(goal_id: int, user: dict = Depends(get_current_user)):
    row = await goal_service.get_goal(user["id"], goal_id)
    if row is None:
        raise HTTPException(404, detail="Goal not found")
    return row


@goals_router.get("/{goal_id}/tasks", response_model=list[TaskOut])
async def goal_tasks(goal_id: int, user: dict = Depends(get_current_user)):
    return await goal_service.list_tasks(user["id"], goal_id)


@goals_router.post("/{goal_id}/tasks", response_model=TaskOut, status_code=201)
async def add_task(
    goal_id: int,
    payload: TaskCreate,
    user: dict = Depends(get_current_user),
):
    row = await goal_service.create_task(
        user["id"],
        goal_id,
        title=payload.title,
        description=payload.description,
        agent_profile_key=payload.agent_profile_key,
        depends_on=payload.depends_on,
        acceptance=payload.acceptance,
        risk=payload.risk,
        input=payload.input,
        sort_order=payload.sort_order,
        deadline=payload.deadline,
    )
    if row is None:
        raise HTTPException(404, detail="Goal not found")
    return row


@goals_router.patch("/{goal_id}/tasks/{task_id}", response_model=TaskOut)
async def patch_task(
    goal_id: int,
    task_id: int,
    payload: TaskUpdate,
    user: dict = Depends(get_current_user),
):
    values = payload.model_dump(exclude_unset=True)
    row = await goal_service.update_task(user["id"], task_id, **values)
    if row is None:
        raise HTTPException(404, detail="Task not found")
    return row


@goals_router.post("/{goal_id}/plan")
async def plan(
    goal_id: int,
    force: bool = Query(False),
    user: dict = Depends(get_current_user),
):
    result = await planner.plan_goal(user["id"], goal_id, force=force)
    if result is None:
        raise HTTPException(404, detail="Goal not found")
    return result


@goals_router.post("/{goal_id}/tick")
async def tick(goal_id: int, user: dict = Depends(get_current_user)):
    result = await orchestrator.tick_goal(user["id"], goal_id)
    if result is None:
        raise HTTPException(404, detail="Goal not found")
    return result


@goals_router.post("/{goal_id}/dispatch")
async def dispatch(goal_id: int, user: dict = Depends(get_current_user)):
    result = await dispatch_goal(user["id"], goal_id)
    if result is None:
        raise HTTPException(404, detail="Goal not found")
    return result


@tasks_router.post("/{task_id}/verify")
async def verify(task_id: int, user: dict = Depends(get_current_user)):
    result = await verify_task(user["id"], task_id)
    if result is None:
        raise HTTPException(404, detail="Task not found")
    return result


@workspaces_router.get("/{workspace_id}")
async def workspace_detail(workspace_id: int, user: dict = Depends(get_current_user)):
    row = await workspace_service.workspace_view(user["id"], workspace_id)
    if row is None:
        raise HTTPException(404, detail="Workspace not found")
    return row


@workspaces_router.post("/{workspace_id}/items", status_code=201)
async def workspace_add_item(
    workspace_id: int,
    payload: WorkspaceItemCreate,
    user: dict = Depends(get_current_user),
):
    row = await workspace_service.add_item(
        user["id"],
        workspace_id,
        type=payload.type,
        key=payload.key,
        content=payload.content,
        source=payload.source,
        confidence=payload.confidence,
        created_by=payload.created_by,
    )
    if row is None:
        raise HTTPException(404, detail="Workspace not found")
    return row


@workspaces_router.post("/{workspace_id}/artifacts", status_code=201)
async def workspace_add_artifact(
    workspace_id: int,
    payload: WorkspaceArtifactCreate,
    user: dict = Depends(get_current_user),
):
    row = await workspace_service.add_artifact(
        user["id"],
        workspace_id,
        file_id=payload.file_id,
        kind=payload.kind,
    )
    if row is None:
        raise HTTPException(404, detail="Workspace not found")
    return row


@workspaces_router.get("/{workspace_id}/export")
async def workspace_export(workspace_id: int, user: dict = Depends(get_current_user)):
    data = await workspace_service.export_zip(user["id"], workspace_id)
    if data is None:
        raise HTTPException(404, detail="Workspace not found")
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="workspace-{workspace_id}.zip"'},
    )


@capabilities_router.get("", response_model=list[CapabilityOut])
async def capabilities(
    user: dict = Depends(get_current_user),
):
    rows = list_capabilities(user["id"])
    grants = await authorization.list_grants(user["id"])
    by_key: dict[str, str] = {}
    for grant in reversed(grants):
        by_key[grant.capability_key] = grant.decision
    out = []
    for cap in rows:
        item = capability_dict(cap)
        item["grant"] = by_key.get(cap.key)
        out.append(item)
    return out


@capabilities_router.get("/grants", response_model=list[GrantOut])
async def grants(user: dict = Depends(get_current_user)):
    return await authorization.list_grants(user["id"])


@capabilities_router.post("/grants", response_model=GrantOut, status_code=201)
async def add_grant(payload: GrantCreate, user: dict = Depends(get_current_user)):
    return await authorization.create_grant(
        user["id"],
        payload.capability_key,
        decision=payload.decision,
        scope=payload.scope,
        bot_id=payload.bot_id,
        goal_id=payload.goal_id,
        session_id=payload.session_id,
        agent_profile_key=payload.agent_profile_key,
        constraints=payload.constraints,
        expires_at=payload.expires_at,
    )


@capabilities_router.delete("/grants/{grant_id}")
async def remove_grant(grant_id: int, user: dict = Depends(get_current_user)):
    if not await authorization.revoke_grant(user["id"], grant_id):
        raise HTTPException(404, detail="Grant not found")
    return {"ok": True}
