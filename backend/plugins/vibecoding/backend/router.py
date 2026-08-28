import logging

from fastapi import APIRouter, Depends
from core.auth.dependencies import get_current_user

from plugins.vibecoding.backend.service import hub

log = logging.getLogger("uvicorn")

router = APIRouter(prefix="/api/vibecoding", tags=["vibecoding"])


def register_host_channel():
    """Attach the vibecoding protocol to the shared host channel."""
    hub.register()


@router.get("/devices")
async def list_devices(user: dict = Depends(get_current_user)):
    return {"devices": hub.devices_payload(user["id"])}


@router.get("/tasks")
async def list_tasks(limit: int = 50, user: dict = Depends(get_current_user)):
    return {"tasks": hub.recent_tasks(user["id"], limit)}
