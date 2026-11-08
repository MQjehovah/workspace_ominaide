from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from core.auth.dependencies import get_current_user
from core.auth.jwt import decode_access_token
from core.wschannel import machines as machine_service
from core.wschannel.hub import host_channel

router = APIRouter(tags=["wschannel"])


class RenameMachineRequest(BaseModel):
    name: str = Field(default="", max_length=120)


def _machine_out(row, online_ids: set[str]) -> dict:
    return {
        "machine_id": row.machine_id,
        "name": row.display_name(),
        "default_name": row.default_name,
        "platform": row.platform or "desktop",
        "status": "online" if row.machine_id in online_ids else "offline",
        "online": row.machine_id in online_ids,
        "last_seen": row.last_seen.isoformat() if row.last_seen else None,
    }


@router.get("/api/vibecoding/machines")
async def list_vibecoding_machines(user: dict = Depends(get_current_user)):
    """Known desktop machines for the current user, including offline ones."""
    online_ids = set(host_channel.machine_ids(user["id"]))
    rows = await machine_service.list_machines(user["id"])
    out = [_machine_out(row, online_ids) for row in rows]
    known = {row.machine_id for row in rows}
    # A connection that beat the DB write should still be visible.
    for machine_id in online_ids - known:
        out.append({
            "machine_id": machine_id,
            "name": host_channel.machine_name(machine_id),
            "default_name": host_channel.machine_name(machine_id),
            "platform": "desktop",
            "status": "online",
            "online": True,
            "last_seen": None,
        })
    out.sort(key=lambda item: (not item["online"], item["name"].lower()))
    return out


@router.put("/api/vibecoding/machines/{machine_id}")
async def rename_machine(
    machine_id: str,
    req: RenameMachineRequest,
    user: dict = Depends(get_current_user),
):
    row = await machine_service.rename(user["id"], machine_id, req.name)
    if row is None:
        raise HTTPException(status_code=404, detail="Machine not found")
    if machine_id in host_channel.machine_ids(user["id"]):
        host_channel.set_machine_name(machine_id, row.display_name())
    return _machine_out(row, set(host_channel.machine_ids(user["id"])))


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
    default_name = websocket.query_params.get("machine_name") or machine_id
    try:
        display_name = await machine_service.register(
            user_id, machine_id, default_name
        )
    except Exception:
        display_name = default_name

    await websocket.accept()
    await host_channel.connect_machine(user_id, machine_id, display_name, websocket)
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
        await machine_service.touch(user_id, machine_id)
