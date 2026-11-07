"""Unified MCP management API."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from core.auth.dependencies import get_current_user
from core.database.session import async_session
from core.mcp_hub.hub import _decrypt_json, _encrypt_json, _slugify, mcp_hub
from core.mcp_hub.models import McpCall, McpServer, McpTool
from core.mcp_hub.templates import list_templates


router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class McpServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = None
    scope: str = "backend"
    transport: str = "stdio"
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    enabled: bool = True
    auto_start: bool = True
    risk_default: str = "read"
    tool_allowlist: list[str] | None = None


class McpServerUpdate(BaseModel):
    name: str | None = None
    scope: str | None = None
    transport: str | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    enabled: bool | None = None
    auto_start: bool | None = None
    risk_default: str | None = None
    tool_allowlist: list[str] | None = None


class McpToolUpdate(BaseModel):
    risk: str | None = None
    enabled: bool | None = None


def _tools_count(row: McpServer) -> int:
    return int(getattr(row, "_tool_count", 0) or 0)


def _server_out(row: McpServer) -> dict:
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "scope": row.scope,
        "transport": row.transport,
        "command": row.command,
        "args": row.args or [],
        "env_keys": sorted(_decrypt_json(row.env_encrypted).keys()),
        "url": row.url,
        "header_keys": sorted(_decrypt_json(row.headers_encrypted).keys()),
        "enabled": bool(row.enabled),
        "auto_start": bool(row.auto_start),
        "risk_default": row.risk_default,
        "tool_allowlist": row.tool_allowlist,
        "last_status": row.last_status,
        "last_error": row.last_error,
        "last_connected_at": row.last_connected_at,
        "tools_count": _tools_count(row),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _tool_out(row: McpTool, server: McpServer) -> dict:
    return {
        "id": row.id,
        "server_id": row.server_id,
        "server": server.slug,
        "name": row.name,
        "full_name": f"{server.slug}__{row.name}",
        "description": row.description,
        "input_schema": row.input_schema,
        "risk": row.risk,
        "enabled": bool(row.enabled),
        "discovered_at": row.discovered_at,
    }


async def _load_server(user_id: int, server_id: int) -> McpServer:
    async with async_session() as db:
        row = (await db.execute(
            select(McpServer).where(McpServer.id == server_id, McpServer.user_id == user_id)
        )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return row


@router.get("/templates")
async def templates(user: dict = Depends(get_current_user)):
    return {"templates": list_templates()}


@router.get("/servers")
async def list_servers(user: dict = Depends(get_current_user)):
    async with async_session() as db:
        rows = list((await db.execute(
            select(McpServer).where(McpServer.user_id == user["id"]).order_by(McpServer.id)
        )).scalars().all())
        counts = dict((await db.execute(
            select(McpTool.server_id, func.count(McpTool.id))
            .where(McpTool.server_id.in_([r.id for r in rows] or [0]))
            .group_by(McpTool.server_id)
        )).all())
    for row in rows:
        row._tool_count = counts.get(row.id, 0)
    return {"servers": [_server_out(r) for r in rows]}


@router.post("/servers")
async def create_server(req: McpServerCreate, user: dict = Depends(get_current_user)):
    slug = _slugify(req.slug or req.name)
    # Tool names are global. A shared "dingtalk" slug would mix users, so every
    # DingTalk server is namespaced by owner.
    if slug.startswith("dingtalk") or "钉钉" in (req.name or ""):
        slug = f"dingtalk-{user['id']}"
    if req.transport not in ("stdio", "http"):
        raise HTTPException(status_code=422, detail="transport must be stdio or http")
    # A stdio MCP can run any command inside the backend container, which would
    # break per-user isolation. Only admins may register them; normal users use
    # the built-in DingTalk binding or HTTP MCP servers.
    if req.transport == "stdio" and not user.get("is_admin"):
        raise HTTPException(
            status_code=403,
            detail="普通用户不能创建 stdio MCP；请在设置中绑定钉钉，或使用 HTTP MCP",
        )
    if req.transport == "stdio" and not req.command:
        raise HTTPException(status_code=422, detail="stdio server requires command")
    if req.transport == "http" and not req.url:
        raise HTTPException(status_code=422, detail="http server requires url")
    async with async_session() as db:
        # Tool names are global in the agent registry; keep slugs unique.
        exists = (await db.execute(select(McpServer).where(McpServer.slug == slug))).scalar_one_or_none()
        if exists is not None:
            raise HTTPException(status_code=409, detail=f"slug already in use: {slug}")
        row = McpServer(
            user_id=user["id"],
            slug=slug,
            name=req.name,
            scope=req.scope,
            transport=req.transport,
            command=req.command,
            args=req.args or [],
            env_encrypted=_encrypt_json(req.env),
            url=req.url,
            headers_encrypted=_encrypt_json(req.headers),
            enabled=req.enabled,
            auto_start=req.auto_start,
            risk_default=req.risk_default,
            tool_allowlist=req.tool_allowlist,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    if row.enabled and row.auto_start:
        try:
            await mcp_hub.connect_server(row.id, user["id"])
        except Exception:
            pass
    return _server_out(row)


@router.patch("/servers/{server_id}")
async def update_server(server_id: int, req: McpServerUpdate, user: dict = Depends(get_current_user)):
    server = await _load_server(user["id"], server_id)
    fields = req.model_dump(exclude_unset=True)
    async with async_session() as db:
        row = (await db.execute(
            select(McpServer).where(McpServer.id == server_id, McpServer.user_id == user["id"])
        )).scalar_one()
        if "env" in fields:
            row.env_encrypted = _encrypt_json(fields.pop("env"))
        if "headers" in fields:
            row.headers_encrypted = _encrypt_json(fields.pop("headers"))
        for key, value in fields.items():
            setattr(row, key, value)
        await db.commit()
        await db.refresh(row)
    if row.enabled:
        try:
            await mcp_hub.connect_server(row.id, user["id"])
        except Exception:
            pass
    else:
        await mcp_hub.disconnect_server(row.id)
    return _server_out(row)


@router.delete("/servers/{server_id}")
async def delete_server(server_id: int, user: dict = Depends(get_current_user)):
    await _load_server(user["id"], server_id)
    await mcp_hub.disconnect_server(server_id)
    async with async_session() as db:
        row = (await db.execute(
            select(McpServer).where(McpServer.id == server_id, McpServer.user_id == user["id"])
        )).scalar_one()
        await db.delete(row)
        await db.commit()
    return {"message": "MCP server deleted"}


@router.post("/servers/{server_id}/connect")
async def connect_server(server_id: int, user: dict = Depends(get_current_user)):
    await _load_server(user["id"], server_id)
    try:
        return await mcp_hub.connect_server(server_id, user["id"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/servers/{server_id}/disconnect")
async def disconnect_server(server_id: int, user: dict = Depends(get_current_user)):
    await _load_server(user["id"], server_id)
    await mcp_hub.disconnect_server(server_id)
    return {"status": "disconnected"}


@router.get("/servers/{server_id}/tools")
async def server_tools(server_id: int, user: dict = Depends(get_current_user)):
    server = await _load_server(user["id"], server_id)
    async with async_session() as db:
        rows = list((await db.execute(
            select(McpTool).where(McpTool.server_id == server_id).order_by(McpTool.name)
        )).scalars().all())
    return {"tools": [_tool_out(r, server) for r in rows]}


@router.patch("/servers/{server_id}/tools/{tool_name}")
async def update_tool(
    server_id: int, tool_name: str, req: McpToolUpdate,
    user: dict = Depends(get_current_user),
):
    await _load_server(user["id"], server_id)
    async with async_session() as db:
        row = (await db.execute(
            select(McpTool).where(McpTool.server_id == server_id, McpTool.name == tool_name)
        )).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="MCP tool not found")
        if req.risk is not None:
            if req.risk not in {"read", "write", "exec", "external", "dangerous"}:
                raise HTTPException(status_code=422, detail="invalid risk")
            row.risk = req.risk
        if req.enabled is not None:
            row.enabled = req.enabled
        await db.commit()
    # Re-sync proxies so risk/enabled changes take effect immediately.
    try:
        await mcp_hub.connect_server(server_id, user["id"])
    except Exception:
        pass
    return {"message": "Tool updated"}


@router.get("/calls")
async def list_calls(
    server_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    async with async_session() as db:
        q = select(McpCall).where(McpCall.user_id == user["id"])
        if server_id is not None:
            q = q.where(McpCall.server_id == server_id)
        rows = list((await db.execute(
            q.order_by(McpCall.id.desc()).limit(limit)
        )).scalars().all())
    return {"calls": [{
        "id": r.id,
        "server_id": r.server_id,
        "tool_name": r.tool_name,
        "status": r.status,
        "error": r.error,
        "duration_ms": r.duration_ms,
        "run_id": r.run_id,
        "created_at": r.created_at,
    } for r in rows]}
