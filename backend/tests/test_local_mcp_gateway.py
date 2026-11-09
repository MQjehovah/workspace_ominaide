"""Local MCP gateway: discovery and calls use two stable Bot tools."""

from ai.mcp.tools import local as local_tool
from ai.bots import policy
from core.wschannel import local_tools


def _machine(monkeypatch):
    monkeypatch.setattr(
        local_tools.host_channel, "machine_ids", lambda user_id: ["machine-a"]
    )
    monkeypatch.setattr(
        local_tools.host_channel, "machine_name", lambda machine_id: "Mac mini"
    )


async def test_local_mcp_search_formats_tools(monkeypatch):
    _machine(monkeypatch)

    async def fake_call(user_id, machine_id, tool, args, **kwargs):
        assert tool == "mcp_search"
        assert args["query"] == "filesystem"
        return {
            "ok": True,
            "result": {
                "tools": [
                    {
                        "server_id": "filesystem",
                        "server_name": "Filesystem",
                        "name": "read_file",
                        "description": "Read a file",
                        "input_schema": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                        },
                    }
                ]
            },
        }

    monkeypatch.setattr(local_tools, "call_local", fake_call)
    response = await local_tool.local_mcp_search(1, {"query": "filesystem"})
    text = response.content[0].text
    assert not response.isError
    assert "Filesystem" in text
    assert "read_file" in text
    assert "schema:" in text
    assert "local_mcp_call" in text


async def test_local_mcp_call_returns_content(monkeypatch):
    _machine(monkeypatch)

    async def fake_call(user_id, machine_id, tool, args, **kwargs):
        assert tool == "mcp_call"
        assert args["server_id"] == "filesystem"
        assert args["tool"] == "read_file"
        assert args["arguments"] == {"path": "~/a.txt"}
        return {
            "ok": True,
            "result": {"content": "file body", "is_error": False},
        }

    monkeypatch.setattr(local_tools, "call_local", fake_call)
    response = await local_tool.local_mcp_call(
        1,
        {
            "server_id": "filesystem",
            "tool": "read_file",
            "arguments": {"path": "~/a.txt"},
        },
    )
    assert not response.isError
    assert response.content[0].text == "file body"


def test_local_mcp_risk_defaults():
    risk, decision = policy.decide(
        None, "local_mcp_call", {"server_id": "x", "tool": "y"}
    )
    assert risk == "exec"
    assert decision == "ask"
    risk, decision = policy.decide(None, "local_mcp_search", {"query": "git"})
    assert risk == "read"
    assert decision == "auto"
