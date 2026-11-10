"""Local desktop execution bridge: machine selection and round-trip results."""

import asyncio

from ai.mcp.tools import local as local_tool
from core.wschannel import local_tools


def _text(response) -> str:
    return response.content[0].text


async def test_list_local_machines_empty(monkeypatch):
    monkeypatch.setattr(local_tools.host_channel, "machine_ids", lambda user_id: [])

    response = await local_tool.list_local_machines(1, {})
    assert not response.isError
    assert "没有在线的本地机器" in _text(response)


async def test_local_file_rejects_server_project_path(monkeypatch):
    response = await local_tool.local_file(
        1, {"op": "list", "path": "/data/workspace/1/projects/demo"}
    )
    assert response.isError
    assert "project_file" in _text(response)


async def test_local_shell_requires_machine_when_multiple(monkeypatch):
    names = {"dev-a": "mac-a", "dev-b": "mac-b"}
    monkeypatch.setattr(
        local_tools.host_channel, "machine_ids", lambda user_id: list(names)
    )
    monkeypatch.setattr(
        local_tools.host_channel, "machine_name", lambda machine_id: names[machine_id]
    )

    response = await local_tool.local_shell(1, {"command": "pwd"})
    assert response.isError
    assert "多个本地机器在线" in _text(response)


async def test_local_shell_roundtrip_and_machine_name(monkeypatch):
    calls: list[dict] = []

    monkeypatch.setattr(
        local_tools.host_channel, "machine_ids", lambda user_id: ["dev-a"]
    )
    monkeypatch.setattr(
        local_tools.host_channel, "machine_name", lambda machine_id: "mac-a"
    )

    async def fake_send(user_id, machine_id, channel, data):
        calls.append(data)
        assert channel == "local-tools"
        await asyncio.sleep(0)
        await local_tools._handle_message(
            user_id,
            machine_id,
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

    monkeypatch.setattr(local_tools.host_channel, "send_to_machine", fake_send)

    response = await local_tool.local_shell(
        1, {"command": "pwd", "machine": "mac-a"}
    )
    assert not response.isError, _text(response)
    text = _text(response)
    assert "本地机器：mac-a" in text
    assert "退出码：0" in text
    assert "/Users/me" in text
    assert calls and calls[0]["args"]["command"] == "pwd"


async def test_local_shell_reports_desktop_error(monkeypatch):
    monkeypatch.setattr(
        local_tools.host_channel, "machine_ids", lambda user_id: ["dev-a"]
    )
    monkeypatch.setattr(
        local_tools.host_channel, "machine_name", lambda machine_id: "mac-a"
    )

    async def fake_send(user_id, machine_id, channel, data):
        await asyncio.sleep(0)
        await local_tools._handle_message(
            user_id,
            machine_id,
            {
                "type": "result",
                "call_id": data["call_id"],
                "ok": False,
                "error": "用户拒绝执行本地命令",
            },
            None,
        )
        return True

    monkeypatch.setattr(local_tools.host_channel, "send_to_machine", fake_send)

    response = await local_tool.local_shell(1, {"command": "rm -rf /tmp/x"})
    assert response.isError
    assert "用户拒绝执行本地命令" in _text(response)


def test_local_shell_defers_approval_to_desktop():
    from ai.bots import policy

    risk, decision = policy.decide(None, "local_shell", {"command": "rm -rf /tmp/x"})
    assert risk == "exec"
    # The desktop app owns the ask/always/never policy for local commands.
    assert decision == "auto"


async def test_local_file_tools_roundtrip(monkeypatch):
    def install(handler):
        monkeypatch.setattr(
            local_tools.host_channel, "machine_ids", lambda user_id: ["dev-a"]
        )
        monkeypatch.setattr(
            local_tools.host_channel, "machine_name", lambda machine_id: "mac-a"
        )

        async def fake_send(user_id, machine_id, channel, data):
            await asyncio.sleep(0)
            await local_tools._handle_message(
                user_id,
                machine_id,
                {
                    "type": "result",
                    "call_id": data["call_id"],
                    "ok": True,
                    "result": handler(data),
                },
                None,
            )
            return True

        monkeypatch.setattr(local_tools.host_channel, "send_to_machine", fake_send)

    install(lambda data: {
        "path": "/Users/me/projects",
        "entries": [
            {"name": "src", "type": "dir"},
            {"name": "README.md", "type": "file", "size": 12},
        ],
        "truncated": False,
    })
    response = await local_tool.local_list_dir(1, {"path": "~/projects"})
    assert not response.isError, _text(response)
    assert "[dir] src" in _text(response)
    assert "README.md" in _text(response)

    install(lambda data: {
        "path": "/Users/me/a.txt",
        "size": 5,
        "binary": False,
        "content": "hello",
        "truncated": False,
    })
    response = await local_tool.local_read_file(1, {"path": "~/a.txt"})
    assert not response.isError, _text(response)
    assert "hello" in _text(response)

    install(lambda data: {
        "path": "/Users/me/new.txt",
        "bytes": 5,
        "created": True,
    })
    response = await local_tool.local_write_file(
        1, {"path": "~/new.txt", "content": "hello"}
    )
    assert not response.isError, _text(response)
    assert "已创建" in _text(response)

    install(lambda data: {
        "path": "/Users/me/projects",
        "matches": [{"path": "src/a.ts", "line": 3, "text": "const a = 1"}],
        "truncated": False,
    })
    response = await local_tool.local_grep(
        1, {"pattern": "const", "path": "~/projects"}
    )
    assert not response.isError, _text(response)
    assert "src/a.ts:3: const a = 1" in _text(response)


async def test_local_shell_async_job(monkeypatch):
    calls: list[tuple] = []

    async def fake_call(user_id, machine_id, tool, args, **kwargs):
        calls.append((tool, args))
        return {"ok": True, "result": {"cwd": "/tmp", "pid": 123}}

    monkeypatch.setattr(local_tools, "call_local", fake_call)
    local_tools._jobs.clear()

    job = await local_tools.start_job(1, "dev-a", "echo hi")
    assert job.status == "running"

    await local_tools._handle_message(
        1,
        "dev-a",
        {
            "type": "job_event",
            "job_id": job.job_id,
            "stream": "stdout",
            "chunk": "hi\n",
        },
        None,
    )
    await local_tools._handle_message(
        1,
        "dev-a",
        {
            "type": "job_done",
            "job_id": job.job_id,
            "exit_code": 0,
            "timed_out": False,
            "cancelled": False,
        },
        None,
    )

    current, events, cursor = await local_tools.wait_job(
        1, job.job_id, cursor=0, wait_seconds=1
    )
    assert current.status == "done"
    assert current.exit_code == 0
    assert events == [("stdout", "hi\n")]

    _, no_events, next_cursor = await local_tools.wait_job(
        1, job.job_id, cursor=cursor, wait_seconds=1
    )
    assert no_events == []
    assert next_cursor == cursor


async def test_local_shell_cancel_sends_desktop_call(monkeypatch):
    calls: list[str] = []

    async def fake_call(user_id, machine_id, tool, args, **kwargs):
        calls.append(tool)
        if tool == "shell_cancel":
            return {"ok": True, "result": {"cancelled": True}}
        return {"ok": True, "result": {"cwd": "/tmp"}}

    monkeypatch.setattr(local_tools, "call_local", fake_call)
    local_tools._jobs.clear()

    job = await local_tools.start_job(1, "dev-a", "sleep 100")
    await local_tools.cancel_job(1, job.job_id)
    assert calls == ["shell_start", "shell_cancel"]
