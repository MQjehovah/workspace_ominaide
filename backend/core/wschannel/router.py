from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from core.auth.dependencies import get_current_user
from core.auth.jwt import decode_access_token
from core.config.settings import settings
from core.wschannel import coding_sessions, machines as machine_service
from core.wschannel.hub import host_channel
from core.wschannel.vibecoding import machine_request

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


@router.get("/api/vibecoding/tasks")
async def list_vibecoding_tasks(
    limit: int = 50,
    user: dict = Depends(get_current_user),
):
    """Recent vibecoding tasks for cold-start replay on thin clients."""
    from core.wschannel.vibecoding import recent_tasks

    return {"tasks": recent_tasks(limit)}


@router.delete("/api/vibecoding/machines/{machine_id}")
async def delete_machine(
    machine_id: str,
    user: dict = Depends(get_current_user),
):
    """Remove an offline machine from the local machine list."""
    if machine_id in host_channel.machine_ids(user["id"]):
        raise HTTPException(
            status_code=409,
            detail="该设备当前在线，请先在设备上退出登录后再删除",
        )
    removed = await machine_service.remove(user["id"], machine_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Machine not found")
    return {"deleted": True, "machine_id": machine_id}


class CreateCodingSessionRequest(BaseModel):
    # Optional override; normally the backend picks the configured provider.
    agent: str = ""
    project: str = ""
    title: str = ""


class CodingPromptRequest(BaseModel):
    text: str = ""


async def _machine_call(
    user_id: int,
    machine_id: str,
    action: str,
    payload: dict,
    *,
    timeout: float = 30.0,
) -> dict:
    try:
        result = await machine_request(
            user_id, machine_id, action, payload, timeout=timeout
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    if not result.get("ok"):
        raise HTTPException(
            status_code=502, detail=str(result.get("error") or "桌面端执行失败")
        )
    return result.get("data") or {}


@router.get("/api/vibecoding/sessions")
async def list_coding_sessions(user: dict = Depends(get_current_user)):
    """All last-known coding sessions across the user's machines."""
    rows = await coding_sessions.list_sessions(user["id"])
    online = set(host_channel.machine_ids(user["id"]))
    sessions = [
        {
            "id": row.session_id,
            "session_id": row.session_id,
            "machine_id": row.machine_id,
            "machine_name": host_channel.machine_name(row.machine_id),
            "machine_online": row.machine_id in online,
            "agent": row.agent or "opencode",
            "title": row.title or "未命名会话",
            "project": row.project or "",
            "native": bool(row.native),
            "running": bool(row.running),
            "updated": int(row.updated_ms or 0),
            "last_seen": row.last_seen.isoformat() if row.last_seen else None,
        }
        for row in rows
    ]
    machines = [
        {
            "machine_id": machine_id,
            "name": host_channel.machine_name(machine_id),
            "online": True,
        }
        for machine_id in online
    ]
    return {"sessions": sessions, "machines": machines}


async def _pick_coding_agent(user_id: int, machine_id: str) -> str:
    preferred = (settings.coding_default_provider or "opencode").strip() or "opencode"
    try:
        data = await _machine_call(
            user_id, machine_id, "agents.list", {}, timeout=10
        )
        agents = data.get("agents") or []
    except Exception:
        return preferred if preferred in {"opencode", "codex", "claude"} else "opencode"
    available = [
        str(agent.get("id"))
        for agent in agents
        if isinstance(agent, dict) and agent.get("available")
    ]
    for candidate in (preferred, "opencode", "codex", "claude"):
        if candidate in available:
            return candidate
    return available[0] if available else "opencode"


@router.get("/api/vibecoding/machines/{machine_id}/agents")
async def machine_coding_agents(
    machine_id: str, user: dict = Depends(get_current_user)
):
    return await _machine_call(
        user["id"], machine_id, "agents.list", {}, timeout=15
    )


@router.get("/api/vibecoding/machines/{machine_id}/projects")
async def machine_coding_projects(
    machine_id: str, user: dict = Depends(get_current_user)
):
    return await _machine_call(
        user["id"], machine_id, "project.list", {}, timeout=15
    )


@router.post("/api/vibecoding/machines/{machine_id}/sessions")
async def create_coding_session(
    machine_id: str,
    req: CreateCodingSessionRequest,
    user: dict = Depends(get_current_user),
):
    if not req.project.strip():
        raise HTTPException(status_code=422, detail="请选择项目目录")
    agent = (req.agent or "").strip() or await _pick_coding_agent(
        user["id"], machine_id
    )
    return await _machine_call(
        user["id"],
        machine_id,
        "session.create",
        {
            "agent": agent,
            "project": req.project.strip(),
            "title": req.title.strip(),
        },
        timeout=90,
    )


@router.get("/api/vibecoding/machines/{machine_id}/sessions/{session_id}")
async def coding_session_detail(
    machine_id: str,
    session_id: str,
    limit: int = 150,
    user: dict = Depends(get_current_user),
):
    row = await coding_sessions.get_session(user["id"], machine_id, session_id)
    agent = row.agent if row is not None else "opencode"
    data = await _machine_call(
        user["id"],
        machine_id,
        "session.history",
        {"agent": agent, "session_id": session_id, "limit": limit},
        timeout=60,
    )
    running = bool(data.get("running", row.running if row is not None else False))
    return {
        **data,
        "running": running,
        "streaming": data.get("streaming", ""),
        "streaming_id": data.get("streaming_id", ""),
        "live_tools": data.get("live_tools", []),
        "session": {
            "id": session_id,
            "machine_id": machine_id,
            "agent": agent,
            "title": row.title if row is not None else "",
            "project": row.project if row is not None else "",
            "running": running,
        },
    }


@router.post("/api/vibecoding/machines/{machine_id}/sessions/{session_id}/prompt")
async def coding_session_prompt(
    machine_id: str,
    session_id: str,
    req: CodingPromptRequest,
    user: dict = Depends(get_current_user),
):
    if not req.text.strip():
        raise HTTPException(status_code=422, detail="内容不能为空")
    row = await coding_sessions.get_session(user["id"], machine_id, session_id)
    agent = row.agent if row is not None else "opencode"
    result = await _machine_call(
        user["id"],
        machine_id,
        "session.prompt",
        {
            "agent": agent,
            "session_id": session_id,
            "text": req.text.strip(),
        },
        timeout=90,
    )
    await coding_sessions.set_running(user["id"], machine_id, session_id, True)
    return result


@router.post("/api/vibecoding/machines/{machine_id}/sessions/{session_id}/interrupt")
async def coding_session_interrupt(
    machine_id: str,
    session_id: str,
    user: dict = Depends(get_current_user),
):
    row = await coding_sessions.get_session(user["id"], machine_id, session_id)
    agent = row.agent if row is not None else "opencode"
    result = await _machine_call(
        user["id"],
        machine_id,
        "session.interrupt",
        {"agent": agent, "session_id": session_id},
        timeout=30,
    )
    await coding_sessions.set_running(user["id"], machine_id, session_id, False)
    return result


@router.delete("/api/vibecoding/machines/{machine_id}/sessions/{session_id}")
async def coding_session_delete(
    machine_id: str,
    session_id: str,
    user: dict = Depends(get_current_user),
):
    row = await coding_sessions.get_session(user["id"], machine_id, session_id)
    agent = row.agent if row is not None else "opencode"
    result = await _machine_call(
        user["id"],
        machine_id,
        "session.delete",
        {"agent": agent, "session_id": session_id},
        timeout=30,
    )
    await coding_sessions.remove_session(user["id"], machine_id, session_id)
    return result


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
