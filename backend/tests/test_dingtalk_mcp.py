"""DingTalk MCP server tools and stdio protocol."""
import sys
from pathlib import Path

import pytest

from core.mcp_hub.client import StdioMcpConnection


def test_dingtalk_tool_catalog():
    from mcp_servers.dingtalk.tools import TOOLS

    names = {t["name"] for t in TOOLS}
    assert {"health", "search_messages", "list_unread", "send_message",
            "list_events", "create_event", "list_todos", "create_todo",
            "list_chat_messages", "at_me", "search_contacts", "free_busy",
            "update_event", "cancel_event", "update_todo", "complete_todo",
            "dws_cli"} <= names


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


async def test_read_chat_messages_builds_command(monkeypatch):
    from mcp_servers.dingtalk import tools as dt

    called = []

    async def fake_run(args, timeout=60):
        called.append(args)
        return {"messages": []}

    monkeypatch.setattr(dt, "run_dws", fake_run)

    result = await dt.call_tool("list_chat_messages", {
        "conversation_id": "cid123",
        "start": "2026-11-05T00:00:00+08:00",
        "end": "2026-11-05T23:59:59+08:00",
        "limit": 20,
    })
    assert "ok" in result["content"][0]["text"]
    cmd = called[0]
    assert cmd[:2] == ["chat", "+chat-messages"]
    assert "--conversation-id" in cmd and "cid123" in cmd
    assert "--no-reactions" in cmd
    assert "--limit" in cmd and "20" in cmd

    result = await dt.call_tool("list_chat_messages", {})
    assert result["isError"] is True


async def test_generic_cli_guards_writes_and_destructive_commands(monkeypatch):
    from mcp_servers.dingtalk import tools as dt

    called = []

    async def fake_run(args, timeout=60):
        called.append(args)
        return {"ok": True}

    monkeypatch.setattr(dt, "run_dws", fake_run)

    result = await dt.call_tool("dws_cli", {"args": ["chat", "+chat-list"]})
    assert "ok" in result["content"][0]["text"]
    assert called[0][:2] == ["chat", "+chat-list"]

    result = await dt.call_tool("dws_cli", {"args": ["doc", "+create", "--title", "x"]})
    assert "confirmation_required" in result["content"][0]["text"]
    assert len(called) == 1

    result = await dt.call_tool("dws_cli", {
        "args": ["doc", "+update", "--title", "x"], "confirmed": True,
    })
    assert "ok" in result["content"][0]["text"]
    assert "--yes" in called[-1]

    result = await dt.call_tool("dws_cli", {"args": ["drive", "+delete", "--id", "1"]})
    assert result["isError"] is True
    assert "删除" in result["content"][0]["text"]

    result = await dt.call_tool("dws_cli", {"args": ["chat", "+chat-list", "--yes"]})
    assert result["isError"] is True

    result = await dt.call_tool("dws_cli", {"args": ["auth", "status"]})
    assert result["isError"] is True


async def test_generic_cli_help_returns_plain_text(monkeypatch):
    from mcp_servers.dingtalk import tools as dt

    async def fake_text(args, timeout=60):
        return "Usage: dws chat [flags]\n+chat-list  list chats"

    monkeypatch.setattr(dt, "run_dws_text", fake_text)

    result = await dt.call_tool("dws_cli", {"args": ["help", "chat"]})
    text = result["content"][0]["text"]
    assert "Usage: dws chat" in text
    assert "chat-list" in text


async def test_dingtalk_stdio_server_protocol():
    backend = Path(__file__).resolve().parent.parent
    conn = StdioMcpConnection(sys.executable, ["-m", "mcp_servers.dingtalk.server"], cwd=str(backend))
    try:
        await conn.start()
        tools = await conn.list_tools()
        names = {t["name"] for t in tools}
        assert "search_messages" in names
        assert "create_todo" in names
        assert "list_chat_messages" in names
        assert "dws_cli" in names
    finally:
        await conn.close()
