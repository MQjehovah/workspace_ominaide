"""Private DingTalk MCP client owned by the plugin."""

from __future__ import annotations

import asyncio
import json

from ai.mcp.core import MCPCallResponse
from ai.mcp_hub.hub import mcp_hub
from plugins.dingtalk.backend.service import ensure_dingtalk_server


class DingTalkMcpError(RuntimeError):
    pass


_locks: dict[int, asyncio.Lock] = {}


def _lock(user_id: int) -> asyncio.Lock:
    lock = _locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[user_id] = lock
    return lock


def _response_json(response: MCPCallResponse):
    text = "\n".join(
        c.text for c in (response.content or []) if getattr(c, "text", None)
    ).strip()
    if response.isError:
        raise DingTalkMcpError(text or "钉钉 MCP 调用失败")
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DingTalkMcpError(f"钉钉 MCP 返回格式错误: {text[:200]}") from exc
    if isinstance(data, dict) and data.get("ok") is False:
        raise DingTalkMcpError(str(data.get("error") or "钉钉 MCP 调用失败"))
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    return data


async def server_and_connection(user_id: int):
    server = await ensure_dingtalk_server(user_id)
    await mcp_hub.ensure_connected(server.id, user_id)
    return server


async def call(user_id: int, tool: str, arguments: dict | None = None):
    # stdio MCP requests are serialized per user. Concurrent sync jobs sharing
    # one connection otherwise race with reconnect/timeout handling.
    async with _lock(user_id):
        server = await server_and_connection(user_id)
        response = await mcp_hub.call_external(
            server.id, tool, user_id, arguments or {}
        )
        return _response_json(response)
