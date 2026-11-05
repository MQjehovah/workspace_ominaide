"""DingTalk MCP server tools and stdio protocol."""
import sys
from pathlib import Path

import pytest

from core.mcp_hub.client import StdioMcpConnection


def test_dingtalk_tool_catalog():
    from mcp_servers.dingtalk.tools import TOOLS

    names = {t["name"] for t in TOOLS}
    assert {"health", "search_messages", "list_unread", "send_message",
            "list_events", "create_event", "list_todos", "create_todo"} <= names


async def test_write_tools_require_confirmation(monkeypatch):
    from mcp_servers.dingtalk import tools as dt

    called = []

    async def fake_run(args, timeout=60):
        called.append(args)
        return {"ok": True}

    monkeypatch.setattr(dt, "run_dws", fake_run)

    result = await dt.call_tool("send_message", {"target": "张三", "content": "hi"})
    text = result["content"][0]["text"]
    assert "confirmation_required" in text
    assert not called

    result = await dt.call_tool("send_message", {
        "target": "张三", "content": "hi", "confirmed": True,
    })
    text = result["content"][0]["text"]
    assert "ok" in text
    assert called and "--yes" in called[0]
    assert "chat" in called[0] and "+dm" in called[0]


async def test_search_messages_builds_dws_command(monkeypatch):
    from mcp_servers.dingtalk import tools as dt

    called = []

    async def fake_run(args, timeout=60):
        called.append(args)
        return {"messages": []}

    monkeypatch.setattr(dt, "run_dws", fake_run)

    result = await dt.call_tool("search_messages", {
        "query": "预算", "start": "2026-11-01T00:00:00+08:00", "limit": 20,
    })
    assert "ok" in result["content"][0]["text"]
    cmd = called[0]
    assert cmd[:2] == ["chat", "+search-msg"]
    assert "--query" in cmd and "预算" in cmd
    assert "--start" in cmd and "--page-all" in cmd


async def test_dingtalk_stdio_server_protocol():
    backend = Path(__file__).resolve().parent.parent
    conn = StdioMcpConnection(sys.executable, ["-m", "mcp_servers.dingtalk.server"], cwd=str(backend))
    try:
        await conn.start()
        tools = await conn.list_tools()
        names = {t["name"] for t in tools}
        assert "search_messages" in names
        assert "create_todo" in names
    finally:
        await conn.close()
