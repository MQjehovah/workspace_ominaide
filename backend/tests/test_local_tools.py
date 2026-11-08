"""Local desktop execution bridge: device selection and round-trip results."""

import asyncio

from core.ai.mcp.tools import local as local_tool
from core.wschannel import local_tools


def _text(response) -> str:
    return response.content[0].text


async def test_list_local_devices_empty(monkeypatch):
    monkeypatch.setattr(local_tools.host_channel, "device_ids", lambda user_id: [])

    response = await local_tool.list_local_devices(1, {})
    assert not response.isError
    assert "没有在线的桌面设备" in _text(response)


async def test_local_shell_requires_device_when_multiple(monkeypatch):
    names = {"dev-a": "mac-a", "dev-b": "mac-b"}
    monkeypatch.setattr(
        local_tools.host_channel, "device_ids", lambda user_id: list(names)
    )
    monkeypatch.setattr(
        local_tools.host_channel, "device_name", lambda device_id: names[device_id]
    )

    response = await local_tool.local_shell(1, {"command": "pwd"})
    assert response.isError
    assert "多个桌面设备在线" in _text(response)


async def test_local_shell_roundtrip_and_device_name(monkeypatch):
    calls: list[dict] = []

    monkeypatch.setattr(
        local_tools.host_channel, "device_ids", lambda user_id: ["dev-a"]
    )
    monkeypatch.setattr(
        local_tools.host_channel, "device_name", lambda device_id: "mac-a"
    )

    async def fake_send(user_id, device_id, channel, data):
        calls.append(data)
        assert channel == "local-tools"
        await asyncio.sleep(0)
        await local_tools._handle_message(
            user_id,
            device_id,
            {
                "type": "result",
                "call_id": data["call_id"],
                "ok": True,
                "result": {
                    "stdout": "/Users/me",
                    "stderr": "",
                    "exit_code": 0,
                    "timed_out": False,
                    "cwd": "/Users/me",
                    "duration_ms": 12,
                },
            },
            None,
        )
        return True

    monkeypatch.setattr(local_tools.host_channel, "send_to_host", fake_send)

    response = await local_tool.local_shell(
        1, {"command": "pwd", "device": "mac-a"}
    )
    assert not response.isError, _text(response)
    text = _text(response)
    assert "设备：mac-a" in text
    assert "退出码：0" in text
    assert "/Users/me" in text
    assert calls and calls[0]["args"]["command"] == "pwd"


async def test_local_shell_reports_desktop_error(monkeypatch):
    monkeypatch.setattr(
        local_tools.host_channel, "device_ids", lambda user_id: ["dev-a"]
    )
    monkeypatch.setattr(
        local_tools.host_channel, "device_name", lambda device_id: "mac-a"
    )

    async def fake_send(user_id, device_id, channel, data):
        await asyncio.sleep(0)
        await local_tools._handle_message(
            user_id,
            device_id,
            {
                "type": "result",
                "call_id": data["call_id"],
                "ok": False,
                "error": "用户拒绝执行本地命令",
            },
            None,
        )
        return True

    monkeypatch.setattr(local_tools.host_channel, "send_to_host", fake_send)

    response = await local_tool.local_shell(1, {"command": "rm -rf /tmp/x"})
    assert response.isError
    assert "用户拒绝执行本地命令" in _text(response)
