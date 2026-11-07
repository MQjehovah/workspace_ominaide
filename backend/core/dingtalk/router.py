"""Per-user DingTalk binding API."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core.auth.dependencies import get_current_user
from core.dingtalk import service

router = APIRouter(prefix="/api/dingtalk", tags=["dingtalk"])


@router.get("/status")
async def status(user: dict = Depends(get_current_user)):
    return await service.dingtalk_status(user["id"])


@router.post("/login/start")
async def login_start(user: dict = Depends(get_current_user)):
    session = await service.start_login(user["id"])
    return service.session_out(session)


@router.get("/login/status")
async def login_status(user: dict = Depends(get_current_user)):
    session = service.get_login_session(user["id"])
    if session is None:
        state = await service.dingtalk_status(user["id"])
        if state.get("authenticated"):
            return {"status": "authorized"}
        return {"status": "idle"}
    return service.session_out(session)


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    return await service.logout(user["id"])
