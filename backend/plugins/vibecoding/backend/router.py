import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from core.auth.dependencies import get_current_user

from plugins.vibecoding.backend.service import hub

log = logging.getLogger("uvicorn")

router = APIRouter(prefix="/api/vibecoding", tags=["vibecoding"])
ws_router = APIRouter(tags=["vibecoding"])


def register_host_channel():
    """Attach the vibecoding protocol to the shared host channel."""
    hub.register()


@router.get("/devices")
async def list_devices(user: dict = Depends(get_current_user)):
    return {"devices": hub.devices_payload(user["id"])}


@router.get("/tasks")
async def list_tasks(limit: int = 50, user: dict = Depends(get_current_user)):
    return {"tasks": hub.recent_tasks(user["id"], limit)}


@ws_router.websocket("/ws/vibecoding")
async def vibecoding_ws(websocket: WebSocket):
    """Mobile viewer/controller endpoint.

    Desktop executors no longer connect here — they ride the shared
    `/ws/host` channel with `channel: "vibecoding"` messages.
    """
    token = websocket.query_params.get("token")
    from core.auth.jwt import decode_access_token
    payload = decode_access_token(token) if token else None
    if not payload:
        await websocket.close(code=4001)
        return
    user_id = int(payload["sub"])

    await websocket.accept()
    await hub.connect_mobile(user_id, websocket)
    log.info(f"[vibecoding] mobile connected user={user_id}")
    try:
        await websocket.send_json({"type": "device.status", "devices": hub.devices_payload(user_id)})
        await websocket.send_json({"type": "tasks.snapshot", "tasks": hub.recent_tasks(user_id, 50)})
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")
            if msg_type == "task.dispatch":
                dispatch = {
                    "type": "task.dispatch",
                    "task_id": msg.get("task_id"),
                    "tool": msg.get("tool"),
                    "project": msg.get("project"),
                    "input": msg.get("input"),
                    "source": "mobile",
                }
                target = msg.get("device_id")
                if target:
                    if not await hub.send_to_desktop(user_id, target, dispatch):
                        await websocket.send_json({
                            "type": "dispatch.error",
                            "task_id": msg.get("task_id"),
                            "reason": "目标设备不在线",
                        })
                else:
                    sent = await hub.broadcast_to_desktops(user_id, dispatch)
                    if not sent:
                        await websocket.send_json({
                            "type": "dispatch.error",
                            "task_id": msg.get("task_id"),
                            "reason": "没有在线的桌面设备",
                        })
            elif msg_type == "task.control":
                control = {
                    "type": "task.control",
                    "task_id": msg.get("task_id"),
                    "action": msg.get("action", "cancel"),
                }
                target = hub.task_device.get(msg.get("task_id") or "")
                if target:
                    await hub.send_to_desktop(user_id, target, control)
                else:
                    await hub.broadcast_to_desktops(user_id, control)
            elif msg_type == "projects.request":
                request_id = msg.get("request_id") or ""
                hub.register_pending(request_id, websocket)
                request = {"type": "projects.request", "request_id": request_id}
                target = msg.get("device_id")
                if target:
                    await hub.send_to_desktop(user_id, target, request)
                else:
                    await hub.broadcast_to_desktops(user_id, request)
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect_mobile(user_id, websocket)
        log.info(f"[vibecoding] mobile disconnected user={user_id}")
