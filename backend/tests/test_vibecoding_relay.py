from core.wschannel import vibecoding


class _FakeWs:
    pass


async def test_viewer_request_is_routed_to_machine(monkeypatch):
    calls = []

    async def fake_send(user_id, machine_id, channel, data):
        calls.append((user_id, machine_id, channel, data))
        return True

    monkeypatch.setattr(vibecoding.host_channel, "send_to_machine", fake_send)
    payload = {
        "type": "oc.request",
        "request_id": "r1",
        "action": "sessions.list",
        "machine_id": "m1",
        "payload": {"limit": 10},
    }
    await vibecoding._handle_message(7, "", payload, _FakeWs())

    assert calls, "request should be forwarded to the desktop machine"
    user_id, machine_id, channel, data = calls[0]
    assert (user_id, machine_id, channel) == (7, "m1", "vibecoding")
    assert data["type"] == "oc.request"
    assert data["request_id"] == "r1"


async def test_machine_response_goes_back_to_requesting_viewer(monkeypatch):
    forwarded = []
    replies = []

    async def fake_send(user_id, machine_id, channel, data):
        forwarded.append(data)
        return True

    async def fake_to_ws(ws, channel, data):
        replies.append((ws, data))
        return True

    monkeypatch.setattr(vibecoding.host_channel, "send_to_machine", fake_send)
    monkeypatch.setattr(vibecoding.host_channel, "send_to_ws", fake_to_ws)

    viewer = _FakeWs()
    await vibecoding._handle_message(
        7,
        "",
        {
            "type": "oc.request",
            "request_id": "r2",
            "action": "session.history",
            "machine_id": "m1",
            "payload": {"session_id": "ses_1"},
        },
        viewer,
    )
    assert forwarded

    await vibecoding._handle_message(
        7,
        "m1",
        {"type": "oc.response", "request_id": "r2", "ok": True, "data": {"messages": []}},
        _FakeWs(),
    )

    assert replies, "response should be delivered to the requesting viewer"
    ws, data = replies[-1]
    assert ws is viewer
    assert data["ok"] is True
    assert data["request_id"] == "r2"


async def test_offline_machine_returns_error(monkeypatch):
    replies = []

    async def fake_send(user_id, machine_id, channel, data):
        return False

    async def fake_to_ws(ws, channel, data):
        replies.append(data)
        return True

    monkeypatch.setattr(vibecoding.host_channel, "send_to_machine", fake_send)
    monkeypatch.setattr(vibecoding.host_channel, "send_to_ws", fake_to_ws)

    await vibecoding._handle_message(
        7,
        "",
        {
            "type": "oc.request",
            "request_id": "r3",
            "action": "sessions.list",
            "machine_id": "m-offline",
            "payload": {},
        },
        _FakeWs(),
    )

    assert replies
    assert replies[-1]["type"] == "oc.response"
    assert replies[-1]["ok"] is False
    assert "不在线" in replies[-1]["error"]


async def test_task_ring_buffer_tracks_lifecycle():
    vibecoding._tasks.clear()
    vibecoding._task_machine.clear()
    vibecoding._remember_task(
        {
            "task_id": "t-relay",
            "event": "started",
            "machine_id": "m1",
            "data": {"tool": "opencode", "project": "/tmp/demo", "input": "hi"},
        }
    )
    vibecoding._remember_task(
        {
            "task_id": "t-relay",
            "event": "done",
            "data": {"duration_ms": 1234, "code": 0, "output": "finished"},
        }
    )

    tasks = vibecoding.recent_tasks()
    task = next(item for item in tasks if item["task_id"] == "t-relay")
    assert task["status"] == "done"
    assert task["tool"] == "opencode"
    assert task["machine_id"] == "m1"
    assert task["output"] == "finished"
    assert "t-relay" not in vibecoding._task_machine
