"""Unified tool gateway: exposure, search, call and risk propagation."""

import json

from core.ai.mcp.core import MCPCallResponse, MCPContent, MCPTool
from core.ai.mcp.gateway import (
    DEFAULT_PINNED_TOOLS,
    display_target,
    select_exposed_tools,
    tool_call,
    tool_search,
)
from core.ai.mcp.registry import tool_registry
from core.bots import policy


class DummyBot:
    user_id = 1
    allowed_tools = None
    pinned_tools = None


def _fake_tool(name: str, source: str = "plugin", description: str = ""):
    return MCPTool(
        name=name,
        description=description,
        inputSchema={
            "type": "object",
            "properties": {"x": {"type": "string"}},
        },
        source=source,
    )


async def test_search_finds_tool_and_call_executes(monkeypatch):
    name = "fake_mail_search"

    async def handler(user_id, args):
        return MCPCallResponse(
            content=[MCPContent(text=f"ok:{args.get('x', '')}")]
        )

    tool_registry.register(
        _fake_tool(name, description="搜索测试邮件"), handler
    )
    try:
        response = await tool_search(1, {"query": "邮件"})
        assert not response.isError
        payload = json.loads(response.content[0].text)
        assert any(
            item["tool_id"] == f"plugin:{name}" for item in payload["tools"]
        )

        response = await tool_call(
            1,
            {
                "tool_id": f"plugin:{name}",
                "arguments": {"x": "hello"},
            },
        )
        assert not response.isError
        assert response.content[0].text == "ok:hello"
    finally:
        tool_registry.unregister(name)


async def test_tool_call_rejects_gateway_and_unknown():
    response = await tool_call(1, {"tool_id": "builtin:tool_call"})
    assert response.isError
    assert "网关" in response.content[0].text

    response = await tool_call(1, {"tool_id": "plugin:definitely_missing"})
    assert response.isError
    assert "不存在" in response.content[0].text


async def test_tool_call_risk_uses_underlying_tool():
    risk, decision = policy.decide(
        None,
        "tool_call",
        {"tool_id": "plugin:google_gmail_send", "arguments": {}},
    )
    assert (risk, decision) == ("external", "ask")

    risk, decision = policy.decide(
        None, "tool_call", {"tool_id": "plugin:list_todo_items"}
    )
    assert (risk, decision) == ("read", "auto")

    risk, decision = policy.decide(
        None, "tool_call", {"tool_id": "local:m1:filesystem:read_file"}
    )
    assert (risk, decision) == ("exec", "ask")

    risk, decision = policy.decide(
        None, "tool_call", {"tool_id": "local:local_shell"}
    )
    # Desktop approval handles local execution; the bot-level risk is exec.
    assert (risk, decision) == ("exec", "auto")

    risk, decision = policy.decide(
        None,
        "tool_call",
        {"tool_id": "local:local_file", "arguments": {"op": "write"}},
    )
    assert (risk, decision) == ("write", "auto")

    _, decision = policy.decide(
        None, "tool_call", {"tool_id": "builtin:tool_search"}
    )
    assert decision == "deny"


async def test_local_file_dispatches_by_op(monkeypatch):
    from core.ai.mcp.tools import local as local_module

    calls: list[str] = []

    async def fake_list(user_id, args):
        calls.append("list")
        return MCPCallResponse(content=[MCPContent(text="list ok")])

    async def fake_read(user_id, args):
        calls.append("read")
        return MCPCallResponse(content=[MCPContent(text="read ok")])

    async def fake_write(user_id, args):
        calls.append("write")
        return MCPCallResponse(content=[MCPContent(text="write ok")])

    async def fake_grep(user_id, args):
        calls.append("grep")
        return MCPCallResponse(content=[MCPContent(text="grep ok")])

    monkeypatch.setattr(local_module, "local_list_dir", fake_list)
    monkeypatch.setattr(local_module, "local_read_file", fake_read)
    monkeypatch.setattr(local_module, "local_write_file", fake_write)
    monkeypatch.setattr(local_module, "local_grep", fake_grep)

    for op, expected in (
        ("list", "list"),
        ("read", "read"),
        ("write", "write"),
        ("grep", "grep"),
    ):
        response = await local_module.local_file(1, {"op": op, "path": "~/a"})
        assert not response.isError
        assert calls[-1] == expected


def test_exposure_never_includes_local_tools(monkeypatch):
    from core.ai.mcp import gateway

    tools = [
        _fake_tool(name)
        for name in list(DEFAULT_PINNED_TOOLS)
        + ["some_plugin_tool", "local_shell", "local_file"]
    ]
    for tool in tools:
        if tool.name.startswith("local_"):
            tool.source = "local"

    monkeypatch.setattr(gateway, "_online_machine_ids", lambda uid: ["machine-a"])
    exposed = {t.name for t in select_exposed_tools(tools, DummyBot())}
    assert "tool_search" in exposed
    assert "tool_call" in exposed
    assert "local_shell" not in exposed
    assert "local_file" not in exposed
    assert "skill_search" in exposed
    assert "skill_call" in exposed
    assert "some_plugin_tool" not in exposed

    class PinnedBot(DummyBot):
        pinned_tools = ["some_plugin_tool", "local_shell"]

    exposed = {t.name for t in select_exposed_tools(tools, PinnedBot())}
    assert "some_plugin_tool" in exposed
    assert "local_shell" not in exposed

def test_exposure_respects_allowed_tools():
    tools = [
        _fake_tool(name)
        for name in list(DEFAULT_PINNED_TOOLS) + ["some_plugin_tool"]
    ]

    class AllowedBot(DummyBot):
        allowed_tools = ["some_plugin_tool"]

    exposed = {t.name for t in select_exposed_tools(tools, AllowedBot())}
    assert exposed == {"tool_search", "tool_call", "some_plugin_tool"}


def test_local_tools_are_local_source():
    from core.ai.mcp.tools import local

    assert local.TOOLS
    assert all(tool.source == "local" for tool, _ in local.TOOLS)


def test_display_target_unwraps_gateway_call():
    assert display_target("google_gmail_send", {"x": 1}) == (
        "google_gmail_send",
        {"x": 1},
    )
    assert display_target(
        "tool_call",
        {
            "tool_id": "plugin:google_gmail_send",
            "arguments": {"to": "a@b.c"},
        },
    ) == ("google_gmail_send", {"to": "a@b.c"})
    assert display_target(
        "tool_call",
        {
            "tool_id": "local:local_shell",
            "arguments": {"command": "ls"},
        },
    ) == ("local_shell", {"command": "ls"})
    assert display_target(
        "tool_call",
        {
            "tool_id": "local:m1:filesystem:read_file",
            "arguments": {"path": "~/a"},
        },
    ) == ("local_mcp:filesystem/read_file", {"path": "~/a"})


async def test_local_tools_only_via_machine_scope(monkeypatch):
    from core.ai.mcp import gateway

    name = "local_shell"

    async def handler(user_id, args):
        return MCPCallResponse(content=[MCPContent(text="ok")])

    tool = _fake_tool(name, description="run shell on the local machine")
    tool.source = "local"
    tool_registry.register(tool, handler)

    async def fake_local_search(user_id, query, **kwargs):
        return [], None

    monkeypatch.setattr(gateway, "_online_machine_ids", lambda uid: ["machine-a"])
    monkeypatch.setattr(gateway, "search_local_tools", fake_local_search)
    try:
        response = await tool_search(1, {"query": "shell", "scope": "server"})
        payload = json.loads(response.content[0].text)
        assert all(item["name"] != name for item in payload["tools"])

        response = await tool_search(1, {"query": "shell", "scope": "machine"})
        payload = json.loads(response.content[0].text)
        assert any(item["tool_id"] == f"local:{name}" for item in payload["tools"])

        # ``local`` remains an alias for ``machine``.
        response = await tool_search(1, {"query": "shell", "scope": "local"})
        payload = json.loads(response.content[0].text)
        assert payload["scope"] == "machine"
    finally:
        tool_registry.unregister(name)


async def test_local_mcp_search_and_call(monkeypatch):
    from core.ai.mcp.tools import local as local_module
    from core.wschannel import local_tools

    calls: list[tuple] = []

    async def fake_call(user_id, machine_id, tool, args, **kwargs):
        calls.append((machine_id, tool, args))
        if tool == "mcp_search":
            return {
                "ok": True,
                "result": {
                    "tools": [
                        {
                            "server_id": "browser",
                            "server_name": "Browser",
                            "name": "open_page",
                            "description": "Open a page",
                            "input_schema": {"type": "object"},
                        }
                    ]
                },
            }
        return {
            "ok": True,
            "result": {"content": "page opened", "is_error": False},
        }

    monkeypatch.setattr(
        local_module, "_resolve_machine", lambda uid, args: "machine-a"
    )
    monkeypatch.setattr(local_tools, "call_local", fake_call)
    monkeypatch.setattr(
        local_tools.host_channel, "machine_name", lambda mid: "Mac mini"
    )

    response = await tool_search(
        1, {"query": "browser", "scope": "local"}
    )
    payload = json.loads(response.content[0].text)
    tool_id = payload["tools"][0]["tool_id"]
    assert tool_id == "local:machine-a:browser:open_page"

    response = await tool_call(
        1,
        {"tool_id": tool_id, "arguments": {"url": "https://example.com"}},
    )
    assert not response.isError
    assert response.content[0].text == "page opened"
    assert calls[-1][1] == "mcp_call"
    assert calls[-1][2]["server_id"] == "browser"
    assert calls[-1][2]["tool"] == "open_page"
