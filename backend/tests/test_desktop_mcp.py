"""Desktop-scoped MCP proxy: tool registration and call forwarding."""

import asyncio

from core.ai.mcp.core import MCPCallRequest
from core.ai.mcp.registry import tool_registry
from core.bots import policy
from core.wschannel import desktop_mcp


def _tools():
    return [
        {
            "server_id": "filesystem",
            "server_name": "Filesystem",
            "name": "read_file",
            "description": "Read a local file",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        }
    ]


async def test_desktop_mcp_registers_and_calls(monkeypatch):
    desktop_mcp._unregister_machine(1, "machine-a")
    desktop_mcp._register_tools(1, "machine-a", _tools())
    names = desktop_mcp._machine_tools[(1, "machine-a")]
    assert names
    name = names[0]
    assert name.startswith("local_mcp_")
    assert policy.resolve_risk(None, name) == "exec"

    calls: list[dict] = []

    async def fake_send(user_id, machine_id, channel, data):
        calls.append(data)
        await asyncio.sleep(0)
        await desktop_mcp._handle_message(
            user_id,
            machine_id,
            {
                "type": "result",
                "call_id": data["call_id"],
                "ok": True,
                "content": "hello from local mcp",
            },
            None,
        )
        return True

    monkeypatch.setattr(
        desktop_mcp.host_channel, "send_to_machine", fake_send
    )
    response = await tool_registry.call(
        1, MCPCallRequest(name=name, arguments={"path": "~/a.txt"})
    )
    assert not response.isError
    assert "hello from local mcp" in response.content[0].text
    assert calls and calls[0]["server_id"] == "filesystem"
    assert calls[0]["tool"] == "read_file"

    desktop_mcp._unregister_machine(1, "machine-a")
    assert tool_registry.get_handler(name) is None


async def test_desktop_mcp_tools_update_removes_old_tools():
    desktop_mcp._unregister_machine(1, "machine-b")
    desktop_mcp._register_tools(1, "machine-b", _tools())
    old_name = desktop_mcp._machine_tools[(1, "machine-b")][0]

    desktop_mcp._register_tools(
        1,
        "machine-b",
        [
            {
                "server_id": "git",
                "server_name": "Git",
                "name": "status",
                "description": "git status",
                "input_schema": {"type": "object", "properties": {}},
            }
        ],
    )
    new_name = desktop_mcp._machine_tools[(1, "machine-b")][0]
    assert new_name != old_name
    assert tool_registry.get_handler(old_name) is None
    assert tool_registry.get_handler(new_name) is not None

    desktop_mcp._unregister_machine(1, "machine-b")
