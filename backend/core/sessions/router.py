"""Unified session API shared by chat, coding and goal views."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.auth.dependencies import get_current_user
from core.sessions import service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    session_id: str | None = None
    bot_id: int | None = None
    kind: str | None = None
    title: str | None = None
    objective: str | None = None
    metadata: dict = Field(default_factory=dict)


class SessionUpdate(BaseModel):
    title: str | None = None
    objective: str | None = None
    status: str | None = None
    metadata: dict | None = None
    active_run_id: int | None = None


class MessageCreate(BaseModel):
    role: str = "user"
    content: str
    run_id: int | None = None
    kind: str = "text"
    metadata: dict = Field(default_factory=dict)


@router.get("")
async def list_sessions(
    kind: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    return {"sessions": await service.list_sessions(user["id"], kind=kind, limit=limit)}


@router.post("")
async def create_session(req: SessionCreate, user: dict = Depends(get_current_user)):
    return await service.create_session(
        user["id"],
        bot_id=req.bot_id,
        kind=req.kind,
        title=req.title,
        objective=req.objective,
        metadata=req.metadata,
        session_id=req.session_id,
    )


@router.get("/{session_id}")
async def get_session(session_id: str, user: dict = Depends(get_current_user)):
    session = await service.get_session(user["id"], session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.patch("/{session_id}")
async def update_session(
    session_id: str,
    req: SessionUpdate,
    user: dict = Depends(get_current_user),
):
    values = {key: value for key, value in req.model_dump().items() if value is not None}
    session = await service.update_session(user["id"], session_id, **values)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    if not await service.delete_session(user["id"], session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted"}


@router.get("/{session_id}/messages")
async def list_messages(
    session_id: str,
    limit: int = Query(100, ge=1, le=500),
    before_id: int | None = Query(None),
    user: dict = Depends(get_current_user),
):
    session = await service.get_session(user["id"], session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"messages": await service.list_messages(user["id"], session_id, limit=limit, before_id=before_id)}


@router.post("/{session_id}/messages")
async def add_message(
    session_id: str,
    req: MessageCreate,
    user: dict = Depends(get_current_user),
):
    session = await service.get_session(user["id"], session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return await service.add_message(
        user["id"],
        session_id,
        req.role,
        req.content,
        bot_id=session.get("bot_id"),
        run_id=req.run_id,
        kind=req.kind,
        metadata=req.metadata,
    )


@router.get("/{session_id}/runs")
async def list_session_runs(
    session_id: str,
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    session = await service.get_session(user["id"], session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    return {"runs": await service.list_runs(user["id"], session_id, limit=limit)}
