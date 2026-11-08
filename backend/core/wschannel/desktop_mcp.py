"""Proxy local desktop MCP servers into the server-side Bot tool registry.

The desktop owns the MCP processes (stdio/http). It sends its tool list over
the `/ws/host` channel; the server registers namespaced tools and forwards
calls back to the same desktop. No inbound port on the desktop is required.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid

from core.ai.mcp.core import MCPCallResponse, MCPContent, MCPTool
from core.ai.mcp.registry import tool_registry
from core.bots import policy
from core.logging import get_logger
from core.wschannel.hub import host_channel

log = get_logger(__name__)

CHANNEL = "local-mcp"
TIMEOUT_SECONDS = 120

_pending: dict[str, asyncio.Future] = {}
_machine_tools: dict[tuple[int, str], list[str]] = {}
_tool_index: dict[str, tuple[str, str, str]] = {}


class DesktopMcpError(RuntimeError):
    pass


def _safe(value: str, limit: int = 24) -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]+", "_", value or "").strip("_")
    return (text or "tool")[:limit]


def _tool_name(machine_id: str, server_id: str, tool: str) -> str:
    digest = uuid.uuid5(uuid.NAMESPACE_URL, machine_id).hex[:6]
    return f"local_mcp_{digest}_{_safe(server_id, 16)}_{_safe(tool, 28)}"


def _unregister_machine(user_id: int, machine_id: str) -> None:
    for name in _machine_tools.pop((user_id, machine_id), []):
        _tool_index.pop(name, None)
        try:
            tool_registry.unregister(name)
            policy.unregister_tool_risk(name)
        except Exception:
            pass


def _register_tools(user_id: int, machine_id: str, tools: list[dict]) -> None:
    _unregister_machine(user_id, machine_id)
    machine_name = host_channel.machine_name(machine_id)
    names: list[str] = []
    used: set[str] = set()
    for item in tools:
        server_id = str(item.get("server_id") or "").strip()
        server_name = str(item.get("server_name") or server_id).strip()
        tool_name = str(item.get("name") or "").strip()
        if not server_id or not tool_name:
            continue
        name = _tool_name(machine_id, server_id, tool_name)
        if name in used:
            continue
        used.add(name)
        schema = item.get("input_schema")
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}}
        description = (
            f"[本地 MCP · {machine_name} · {server_name}] "
            f"{item.get('description') or tool_name}"
        )

        async def handler(
            uid: int,
            args: dict,
            _machine_id: str = machine_id,
            _server_id: str = server_id,
            _tool_name: str = tool_name,
        ) -> MCPCallResponse:
            return await call_tool(uid, _machine_id, _server_id, _tool_name, args)

        tool_registry.register(
            MCPTool(
                name=name,
                description=description,
                inputSchema=schema,
                source="desktop",
                risk="exec",
                user_id=user_id,
            ),
            handler,
        )
        policy.register_tool_risk(name, "exec")
        _tool_index[name] = (machine_id, server_id, tool_name)
        names.append(name)
    _machine_tools[(user_id, machine_id)] = names
    if names:
        log.info(
            f"[local-mcp] {user_id}/{machine_id}: {len(names)} tool(s) registered"
        )


async def _handle_message(user_id: int, machine_id: str, payload: dict, ws) -> None:
    message_type = payload.get("type")
    if message_type == "tools":
        tools = payload.get("tools")
        if isinstance(tools, list):
            _register_tools(user_id, machine_id, tools)
        return
    if message_type == "result":
        call_id = str(payload.get("call_id") or "")
        future = _pending.get(call_id)
        if future is not None and not future.done():
            future.set_result(payload)


async def _on_disconnect(user_id: int, machine_id: str) -> None:
    _unregister_machine(user_id, machine_id)


def register_channel() -> None:
    host_channel.register(CHANNEL, _handle_message, on_disconnect=_on_disconnect)


async def call_tool(
    user_id: int,
    machine_id: str,
    server_id: str,
    tool_name: str,
    args: dict,
) -> MCPCallResponse:
    loop = asyncio.get_running_loop()
    call_id = uuid.uuid4().hex
    future: asyncio.Future = loop.create_future()
    _pending[call_id] = future
    try:
        sent = await host_channel.send_to_machine(
            user_id,
            machine_id,
            CHANNEL,
            {
                "type": "call",
                "call_id": call_id,
                "server_id": server_id,
                "tool": tool_name,
                "args": args or {},
            },
        )
        if not sent:
            raise DesktopMcpError("本地 MCP 所在的桌面端已离线")
        result = await asyncio.wait_for(future, timeout=TIMEOUT_SECONDS)
    except asyncio.TimeoutError as exc:
        raise DesktopMcpError(f"本地 MCP 调用超时（{TIMEOUT_SECONDS}s）") from exc
    finally:
        _pending.pop(call_id, None)

    if not result.get("ok"):
        return MCPCallResponse(
            isError=True,
            content=[MCPContent(text=str(result.get("error") or "本地 MCP 调用失败"))],
        )
    content = result.get("content")
    if not isinstance(content, str):
        try:
            content = json.dumps(content, ensure_ascii=False)
        except Exception:
            content = str(content)
    return MCPCallResponse(
        isError=bool(result.get("is_error")),
        content=[MCPContent(text=content or "(本地 MCP 返回空结果)")],
    )
