from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from core.auth.dependencies import get_current_user
from ai.cognition import authorization
from ai.cognition.capabilities import capability_dict, list_capabilities
from ai.cognition.proposals import act_proposal, get_proposal, list_proposals
from ai.cognition.schemas import (
    CapabilityOut,
    GrantCreate,
    GrantOut,
    ProposalAct,
    ProposalOut,
)

proposals_router = APIRouter(prefix="/api/proposals", tags=["proposals"])
capabilities_router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])


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
        agent_profile_key=payload.agent_profile_key,
        constraints=payload.constraints,
        expires_at=payload.expires_at,
    )


@capabilities_router.delete("/grants/{grant_id}")
async def remove_grant(grant_id: int, user: dict = Depends(get_current_user)):
    if not await authorization.revoke_grant(user["id"], grant_id):
        raise HTTPException(404, detail="Grant not found")
    return {"ok": True}
