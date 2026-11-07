from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from core.auth.dependencies import get_current_user
from core.auth.jwt import decode_access_token
from core.wschannel.hub import host_channel

router = APIRouter(tags=["wschannel"])


@router.get("/api/vibecoding/devices")
async def list_vibecoding_devices(user: dict = Depends(get_current_user)):
    """Connected desktop hosts for the current user.

    The Hub only knows live WebSocket hosts; after a backend restart the
    desktop reconnects and repopulates this list.
    """
    return [
        {
            "device_id": device_id,
            "name": host_channel.device_name(device_id),
            "platform": "desktop",
            "status": "online",
        }
        for device_id in host_channel.device_ids(user["id"])
    ]


@router.websocket("/ws/host")
async def host_channel_ws(websocket: WebSocket):
    """The single multiplexed channel for every client.

    role=desktop (default): an OmniAide desktop host; requires device_id and
      registers as that user's execution device.
    role=viewer: a thin client (mobile etc.); receives channel broadcasts and
      may send channel-tagged commands.
    """
    token = websocket.query_params.get("token")
    payload = decode_access_token(token) if token else None
    if not payload:
        await websocket.close(code=4001)
        return
    user_id = int(payload["sub"])
    role = websocket.query_params.get("role", "desktop")

    if role == "viewer":
        await websocket.accept()
        await host_channel.connect_viewer(user_id, websocket)
        try:
            while True:
                msg = await websocket.receive_json()
                if not isinstance(msg, dict):
                    continue
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue
                await host_channel.handle_message(user_id, "", msg, websocket)
        except WebSocketDisconnect:
            pass
        finally:
            host_channel.disconnect_viewer(user_id, websocket)
        return

    device_id = websocket.query_params.get("device_id") or ""
    if not device_id:
        await websocket.close(code=4003)
        return
    name = websocket.query_params.get("device_name") or device_id
    await websocket.accept()
    await host_channel.connect_host(user_id, device_id, name, websocket)
    try:
        while True:
            msg = await websocket.receive_json()
            if not isinstance(msg, dict):
                continue
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            await host_channel.handle_message(user_id, device_id, msg, websocket)
    except WebSocketDisconnect:
        pass
    finally:
        await host_channel.disconnect_host(user_id, device_id)
