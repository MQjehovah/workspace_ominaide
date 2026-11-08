from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from core.auth.dependencies import get_current_user
from core.auth.jwt import decode_access_token
from core.wschannel.hub import host_channel

router = APIRouter(tags=["wschannel"])


@router.get("/api/vibecoding/machines")
async def list_vibecoding_machines(user: dict = Depends(get_current_user)):
    """Connected desktop machines for the current user.

    The Hub only knows live WebSocket machines; after a backend restart the
    desktop reconnects and repopulates this list.
    """
    return [
        {
            "machine_id": machine_id,
            "name": host_channel.machine_name(machine_id),
            "platform": "desktop",
            "status": "online",
        }
        for machine_id in host_channel.machine_ids(user["id"])
    ]


@router.websocket("/ws/host")
async def host_channel_ws(websocket: WebSocket):
    """The single multiplexed channel for every client.

    role=desktop (default): an OmniAide desktop machine; requires machine_id and
      registers as that user's local machine.
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

    machine_id = websocket.query_params.get("machine_id") or ""
    if not machine_id:
        await websocket.close(code=4003)
        return
    name = websocket.query_params.get("machine_name") or machine_id
    await websocket.accept()
    await host_channel.connect_machine(user_id, machine_id, name, websocket)
    try:
        while True:
            msg = await websocket.receive_json()
            if not isinstance(msg, dict):
                continue
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            await host_channel.handle_message(user_id, machine_id, msg, websocket)
    except WebSocketDisconnect:
        pass
    finally:
        await host_channel.disconnect_machine(user_id, machine_id)
