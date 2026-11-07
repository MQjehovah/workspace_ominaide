"""McpHub: unified registry, lifecycle, policy metadata and audit for MCP servers."""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime

from sqlalchemy import select

from core.ai.mcp.core import MCPCallResponse, MCPContent, MCPTool
from core.ai.mcp.registry import tool_registry
from core.bots import policy
from core.crypto import decrypt_secret, encrypt_secret
from core.database.session import async_session
from core.mcp_hub.client import HttpMcpConnection, McpConnection, McpError, StdioMcpConnection
from core.mcp_hub.models import McpCall, McpServer, McpTool

RISK_LEVELS = {"read", "write", "exec", "external", "dangerous"}


def _encrypt_json(value: dict | None) -> str | None:
    if not value:
        return None
    return encrypt_secret(json.dumps(value, ensure_ascii=False))


def _decrypt_json(value: str | None) -> dict:
    if not value:
        return {}
    try:
        return json.loads(decrypt_secret(value))
    except Exception:
        return {}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", (value or "").strip().lower()).strip("-")
    return slug[:64] or "mcp"


def is_dingtalk_server(server: McpServer) -> bool:
    """Detect the built-in DingTalk stdio server.

    Requiring the module argument (not just a slug/name) prevents a user from
    disguising an arbitrary command as DingTalk.
    """
    return any("mcp_servers.dingtalk" in str(arg) for arg in (server.args or []))


async def user_is_admin(user_id: int) -> bool:
    try:
        from core.auth.domain.models import User

        async with async_session() as db:
            row = (await db.execute(
                select(User.is_admin).where(User.id == user_id)
            )).scalar_one_or_none()
        return bool(row)
    except Exception:
        return False


def _infer_risk(tool_name: str, default: str) -> str:
    name = (tool_name or "").lower()
    if any(k in name for k in ("send", "post", "webhook", "publish")):
        return "external"
    if any(k in name for k in ("delete", "remove", "cancel", "revoke")):
        return "dangerous"
    if any(k in name for k in ("create", "update", "write", "set_", "complete", "move", "rename")):
        return "write"
    if any(k in name for k in ("run", "exec", "shell", "command")):
        return "exec"
    return default if default in RISK_LEVELS else "read"


class McpHub:
    def __init__(self):
        self._conns: dict[int, McpConnection] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._proxy_names: dict[int, set[str]] = {}

    async def startup(self) -> None:
        try:
            async with async_session() as db:
                rows = list((await db.execute(
                    select(McpServer).where(
                        McpServer.enabled == True,  # noqa: E712
                        McpServer.auto_start == True,  # noqa: E712
                        McpServer.scope == "backend",
                    )
                )).scalars().all())
            for server in rows:
                try:
                    await self.connect_server(server.id, server.user_id)
                except Exception as e:
                    print(f"[mcp] startup {server.slug} failed: {e}")
        except Exception as e:
            print(f"[mcp] startup error: {e}")

    async def shutdown(self) -> None:
        for server_id in list(self._conns.keys()):
            await self.disconnect_server(server_id)
        self._conns.clear()
        self._proxy_names.clear()

    def _lock(self, server_id: int) -> asyncio.Lock:
        lock = self._locks.get(server_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[server_id] = lock
        return lock

    async def _load_server(self, server_id: int, user_id: int | None = None) -> McpServer | None:
        async with async_session() as db:
            q = select(McpServer).where(McpServer.id == server_id)
            if user_id is not None:
                q = q.where(McpServer.user_id == user_id)
            return (await db.execute(q)).scalar_one_or_none()

    def _make_connection(self, server: McpServer) -> McpConnection:
        if server.transport == "http":
            if not server.url:
                raise McpError("HTTP MCP 服务器缺少 URL")
            return HttpMcpConnection(server.url, _decrypt_json(server.headers_encrypted))
        if not server.command:
            raise McpError("stdio MCP 服务器缺少 command")
        env = _decrypt_json(server.env_encrypted)
        if is_dingtalk_server(server):
            # Force the per-user DWS config + HOME even if an old global
            # DWS_CONFIG_DIR was stored on the row.
            from core.paths import dingtalk_env, ensure_user_workspace

            ensure_user_workspace(server.user_id)
            env.update(dingtalk_env(server.user_id))
        return StdioMcpConnection(
            server.command,
            list(server.args or []),
            env,
        )

    async def connect_server(self, server_id: int, user_id: int | None = None) -> dict:
        server = await self._load_server(server_id, user_id)
        if server is None:
            raise McpError("MCP 服务器不存在")
        if server.transport == "stdio" and not is_dingtalk_server(server):
            if not await user_is_admin(server.user_id):
                raise McpError("普通用户不能运行 stdio MCP")
        async with self._lock(server_id):
            old = self._conns.pop(server_id, None)
            if old:
                await old.close()
            conn = self._make_connection(server)
            try:
                await conn.start()
                tools = await conn.list_tools()
                self._conns[server_id] = conn
                await self._sync_tools(server, tools)
                await self._set_status(server_id, "connected", None)
                return {"status": "connected", "tools": len(tools)}
            except Exception as e:
                try:
                    await conn.close()
                except Exception:
                    pass
                await self._unregister_proxies(server_id)
                await self._set_status(server_id, "error", str(e)[:1000])
                raise

    async def disconnect_server(self, server_id: int) -> None:
        conn = self._conns.pop(server_id, None)
        if conn:
            await conn.close()
        await self._unregister_proxies(server_id)
        await self._set_status(server_id, "disconnected", None)

    async def _set_status(self, server_id: int, status: str, error: str | None) -> None:
        async with async_session() as db:
            row = (await db.execute(select(McpServer).where(McpServer.id == server_id))).scalar_one_or_none()
            if row is not None:
                row.last_status = status
                row.last_error = error
                if status == "connected":
                    row.last_connected_at = datetime.utcnow()
                await db.commit()

    async def _sync_tools(self, server: McpServer, tools: list[dict]) -> None:
        await self._unregister_proxies(server.id)
        names: set[str] = set()
        async with async_session() as db:
            existing = {
                t.name: t for t in (await db.execute(
                    select(McpTool).where(McpTool.server_id == server.id)
                )).scalars().all()
            }
            seen: set[str] = set()
            for item in tools:
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                seen.add(name)
                schema = item.get("inputSchema") or {"type": "object", "properties": {}}
                row = existing.get(name)
                if row is None:
                    row = McpTool(server_id=server.id, name=name)
                    db.add(row)
                row.description = item.get("description") or name
                row.input_schema = schema
                row.risk = row.risk or _infer_risk(name, server.risk_default or "read")
                row.enabled = True
            for name, row in existing.items():
                if name not in seen:
                    await db.delete(row)
            await db.commit()

        for item in tools:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            full_name = f"{server.slug}__{name}"
            risk = _infer_risk(name, server.risk_default or "read")
            tool = MCPTool(
                name=full_name,
                description=f"[{server.name}] {item.get('description') or name}",
                inputSchema=item.get("inputSchema") or {"type": "object", "properties": {}},
                source="mcp",
                server=server.slug,
                risk=risk,
                user_id=server.user_id,
            )

            async def handler(user_id: int, arguments: dict, *, _server_id=server.id, _name=name):
                return await self.call_external(_server_id, _name, user_id, arguments)

            tool_registry.register(tool, handler)
            policy.register_tool_risk(full_name, risk)
            names.add(full_name)
        self._proxy_names[server.id] = names

    async def _unregister_proxies(self, server_id: int) -> None:
        for name in self._proxy_names.pop(server_id, set()):
            tool_registry.unregister(name)
            policy.unregister_tool_risk(name)

    async def _ensure_conn(self, server_id: int, user_id: int | None,
                           force: bool = False) -> McpConnection:
        conn = self._conns.get(server_id)
        if conn is not None and not force and conn.alive:
            return conn
        info = await self.connect_server(server_id, user_id)
        if info.get("status") != "connected":
            raise McpError("MCP 服务器未连接")
        conn = self._conns.get(server_id)
        if conn is None:
            raise McpError("MCP 服务器未连接")
        return conn

    async def call_external(self, server_id: int, tool_name: str, user_id: int,
                            arguments: dict, run_id: int | None = None) -> MCPCallResponse:
        started = time.monotonic()
        status = "ok"
        error = None
        result: dict = {}
        audit_name = tool_name
        try:
            server = await self._load_server(server_id, user_id)
            if server is None:
                raise McpError("MCP 服务器不存在")
            audit_name = f"{server.slug}__{tool_name}"
            conn = await self._ensure_conn(server_id, user_id)
            from core.observability.recorder import trace_span

            try:
                async with trace_span("mcp", f"{server.slug}.{tool_name}"):
                    result = await conn.call_tool(tool_name, arguments or {})
            except McpError as e:
                # A long-lived stdio connection can go stale (transport closed,
                # child restarted). Reconnect once and retry instead of failing.
                if "超时" not in str(e):
                    raise
                print(f"[mcp] {server.slug} 超时，重连后重试 {tool_name}")
                conn = await self._ensure_conn(server_id, user_id, force=True)
                async with trace_span("mcp", f"{server.slug}.{tool_name}"):
                    result = await conn.call_tool(tool_name, arguments or {})
            if result.get("isError"):
                status = "error"
                error = _content_text(result)[:1000]
        except Exception as e:
            status = "error"
            error = str(e)[:1000]
            result = {"isError": True, "content": [{"type": "text", "text": error}]}
        finally:
            duration = int((time.monotonic() - started) * 1000)
            await self._audit(user_id, server_id, audit_name, arguments, result, status, error, duration, run_id)
        return MCPCallResponse(
            content=_to_content(result),
            isError=status != "ok",
        )

    async def _audit(self, user_id: int, server_id: int, tool_name: str,
                     arguments: dict, result: dict, status: str, error: str | None,
                     duration_ms: int, run_id: int | None) -> None:
        try:
            async with async_session() as db:
                db.add(McpCall(
                    user_id=user_id,
                    server_id=server_id,
                    tool_name=tool_name,
                    arguments=_truncate_obj(arguments),
                    status=status,
                    error=error,
                    duration_ms=duration_ms,
                    run_id=run_id,
                ))
                await db.commit()
        except Exception as e:
            print(f"[mcp] audit error: {e}")


def _content_text(result: dict) -> str:
    parts: list[str] = []
    for item in result.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text") or ""))
    if not parts and result.get("structuredContent"):
        return json.dumps(result["structuredContent"], ensure_ascii=False)
    return "\n".join(parts)


def _to_content(result: dict) -> list[MCPContent]:
    out: list[MCPContent] = []
    for item in result.get("content") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            out.append(MCPContent(text=str(item.get("text") or "")))
        else:
            out.append(MCPContent(text=json.dumps(item, ensure_ascii=False)))
    if not out:
        out.append(MCPContent(text=json.dumps(result, ensure_ascii=False)))
    return out


def _truncate_obj(value: dict | None) -> dict | None:
    if not value:
        return value
    try:
        text = json.dumps(value, ensure_ascii=False)
    except Exception:
        return {"_": str(value)[:1000]}
    if len(text) <= 2000:
        return value
    return {"_truncated": text[:2000]}


mcp_hub = McpHub()
