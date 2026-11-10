"""Authenticated backend facade for the sandbox runner.

The browser never talks to the runner directly. This router owns user auth,
workspace ownership checks, HTTP port proxying and terminal WebSocket bridging.
"""

from __future__ import annotations

import asyncio
import json
from urllib.parse import parse_qsl, urlencode

import httpx
import websockets
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from ai.coding.sandbox_client import SandboxClient, SandboxError, get_client
from core.auth.dependencies import get_current_user
from core.auth.jwt import decode_access_token

router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])
security = HTTPBearer(auto_error=False)

_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "authorization",
    "content-length",
}


class WorkspaceCreateIn(BaseModel):
    template: str = "omniaide-base"
    name: str | None = None
    project_path: str | None = None
    ttl_seconds: int | None = None


class ExecIn(BaseModel):
    command: str | list[str]
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int | None = None


def _client() -> SandboxClient:
    try:
        return get_client()
    except SandboxError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


async def get_user_flexible(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    token: str | None = Query(None),
) -> dict:
    raw = credentials.credentials if credentials else token
    payload = decode_access_token(raw) if raw else None
    if payload is None or payload.get("sub") is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"id": int(payload["sub"])}


async def _owned(client: SandboxClient, user: dict, workspace_id: str) -> dict:
    try:
        workspace = await client.get_workspace(workspace_id)
    except SandboxError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if str(workspace.get("owner_id")) != str(user["id"]):
        raise HTTPException(status_code=404, detail="workspace not found")
    return workspace


def _ws_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[len("https://"):]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://"):]
    return base + path


def _ws_user(websocket: WebSocket) -> dict | None:
    token = websocket.query_params.get("token")
    payload = decode_access_token(token) if token else None
    if payload is None or payload.get("sub") is None:
        return None
    return {"id": int(payload["sub"])}


async def _ws_owned(websocket: WebSocket, client: SandboxClient, user: dict, workspace_id: str) -> dict | None:
    try:
        workspace = await client.get_workspace(workspace_id)
    except SandboxError:
        await websocket.close(code=4404)
        return None
    if str(workspace.get("owner_id")) != str(user["id"]):
        await websocket.close(code=4404)
        return None
    return workspace


@router.get("/templates")
async def list_templates(user: dict = Depends(get_current_user)):
    try:
        return await _client().list_templates()
    except SandboxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/templates/{template_id}/build")
async def get_build(template_id: str, user: dict = Depends(get_current_user)):
    try:
        return await _client().get_build(template_id)
    except SandboxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/templates/{template_id}/build")
async def build_template(template_id: str, user: dict = Depends(get_current_user)):
    try:
        return await _client().build_template(template_id)
    except SandboxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/workspaces")
async def list_workspaces(user: dict = Depends(get_current_user)):
    try:
        return await _client().list_workspaces(str(user["id"]))
    except SandboxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/workspaces", status_code=201)
async def create_workspace(body: WorkspaceCreateIn, user: dict = Depends(get_current_user)):
    client = _client()
    try:
        workspace = await client.create_workspace(
            owner_id=str(user["id"]),
            project_path=body.project_path or "",
            template=body.template,
            name=body.name,
            ttl_seconds=body.ttl_seconds,
        )
    except SandboxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    workspace["proxy_base"] = f"/api/sandbox/workspaces/{workspace['id']}/proxy"
    return workspace


@router.get("/workspaces/{workspace_id}")
async def get_workspace(workspace_id: str, user: dict = Depends(get_current_user)):
    client = _client()
    workspace = await _owned(client, user, workspace_id)
    workspace["proxy_base"] = f"/api/sandbox/workspaces/{workspace_id}/proxy"
    return workspace


@router.post("/workspaces/{workspace_id}/start")
async def start_workspace(workspace_id: str, user: dict = Depends(get_current_user)):
    client = _client()
    await _owned(client, user, workspace_id)
    try:
        return await client.start_workspace(workspace_id)
    except SandboxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/workspaces/{workspace_id}/stop")
async def stop_workspace(workspace_id: str, user: dict = Depends(get_current_user)):
    client = _client()
    await _owned(client, user, workspace_id)
    try:
        return await client.stop_workspace(workspace_id)
    except SandboxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str, user: dict = Depends(get_current_user)):
    client = _client()
    await _owned(client, user, workspace_id)
    try:
        return await client.delete_workspace(workspace_id)
    except SandboxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/workspaces/{workspace_id}/logs")
async def workspace_logs(
    workspace_id: str,
    tail: int = Query(200, ge=1, le=2000),
    user: dict = Depends(get_current_user),
):
    client = _client()
    await _owned(client, user, workspace_id)
    try:
        return await client.logs(workspace_id, tail=tail)
    except SandboxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/workspaces/{workspace_id}/exec")
async def exec_command(
    workspace_id: str,
    body: ExecIn,
    user: dict = Depends(get_current_user),
):
    client = _client()
    await _owned(client, user, workspace_id)
    try:
        return await client.exec(
            workspace_id,
            body.command,
            cwd=body.cwd,
            env=body.env,
            timeout_seconds=body.timeout_seconds or 600,
        )
    except SandboxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/workspaces/{workspace_id}/exec/stream")
async def exec_stream(
    workspace_id: str,
    body: ExecIn,
    user: dict = Depends(get_current_user),
):
    client = _client()
    await _owned(client, user, workspace_id)

    async def events():
        try:
            async for event in client.stream_exec(
                workspace_id,
                body.command,
                cwd=body.cwd,
                env=body.env,
                timeout_seconds=body.timeout_seconds or 600,
            ):
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        except SandboxError as exc:
            yield "data: " + json.dumps({"type": "error", "error": str(exc)}) + "\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.api_route(
    "/workspaces/{workspace_id}/proxy/{port}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_http(
    request: Request,
    workspace_id: str,
    port: int,
    path: str,
    user: dict = Depends(get_user_flexible),
):
    client = _client()
    await _owned(client, user, workspace_id)
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(request.url.query, keep_blank_values=True)
        if key != "token"
    ]
    query = urlencode(query_pairs)
    target = f"{client.base_url}/api/workspaces/{workspace_id}/proxy/{port}/{path}"
    if query:
        target += "?" + query
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _HOP_HEADERS
    }
    headers["Authorization"] = f"Bearer {client.token}"
    body = await request.body()
    upstream_client = httpx.AsyncClient(timeout=client.timeout)
    try:
        upstream_request = upstream_client.build_request(
            request.method, target, headers=headers, content=body
        )
        upstream = await upstream_client.send(upstream_request, stream=True)
    except httpx.HTTPError as exc:
        await upstream_client.aclose()
        raise HTTPException(status_code=502, detail=f"proxy failed: {exc}") from exc

    async def body_stream():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await upstream_client.aclose()

    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in _HOP_HEADERS and key.lower() != "content-type"
    }
    return StreamingResponse(
        body_stream(),
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )


@router.websocket("/workspaces/{workspace_id}/proxy/{port}/{path:path}")
async def proxy_websocket(
    websocket: WebSocket,
    workspace_id: str,
    port: int,
    path: str,
) -> None:
    user = _ws_user(websocket)
    if user is None:
        await websocket.close(code=4401)
        return
    client = _client()
    workspace = await _ws_owned(websocket, client, user, workspace_id)
    if workspace is None:
        return
    query = [
        (key, value)
        for key, value in websocket.query_params.multi_items()
        if key != "token"
    ]
    target = _ws_url(client.base_url, f"/api/workspaces/{workspace_id}/proxy/{port}/{path}")
    params = {"token": client.token}
    if query:
        target += "?" + urlencode(query)
        target += "&" + urlencode(params)
    else:
        target += "?" + urlencode(params)

    try:
        upstream = await websockets.connect(
            target, max_size=None, open_timeout=10, ping_interval=20
        )
    except Exception:
        await websocket.close(code=4502)
        return
    await websocket.accept()

    async def upstream_to_client() -> None:
        try:
            async for message in upstream:
                if isinstance(message, bytes):
                    await websocket.send_bytes(message)
                else:
                    await websocket.send_text(message)
        except Exception:
            pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    forward = asyncio.create_task(upstream_to_client())
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            text = message.get("text")
            data = message.get("bytes")
            if text is not None:
                await upstream.send(text)
            elif data is not None:
                await upstream.send(data)
    except WebSocketDisconnect:
        pass
    finally:
        forward.cancel()
        try:
            await upstream.close()
        except Exception:
            pass


@router.websocket("/workspaces/{workspace_id}/terminal")
async def terminal(websocket: WebSocket, workspace_id: str) -> None:
    user = _ws_user(websocket)
    if user is None:
        await websocket.close(code=4401)
        return
    client = _client()
    workspace = await _ws_owned(websocket, client, user, workspace_id)
    if workspace is None:
        return
    target = _ws_url(client.base_url, f"/api/workspaces/{workspace_id}/terminal")
    target += "?" + urlencode({"token": client.token})
    try:
        upstream = await websockets.connect(
            target, max_size=None, open_timeout=10, ping_interval=20
        )
    except Exception:
        await websocket.close(code=4502)
        return
    await websocket.accept()

    async def upstream_to_client() -> None:
        try:
            async for message in upstream:
                if isinstance(message, bytes):
                    await websocket.send_bytes(message)
                else:
                    await websocket.send_text(message)
        except Exception:
            pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    forward = asyncio.create_task(upstream_to_client())
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            text = message.get("text")
            data = message.get("bytes")
            if text is not None:
                await upstream.send(text)
            elif data is not None:
                await upstream.send(data)
    except WebSocketDisconnect:
        pass
    finally:
        forward.cancel()
        try:
            await upstream.close()
        except Exception:
            pass
