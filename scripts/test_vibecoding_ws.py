"""Smoke test for the unified host channel (`/ws/host`): desktop hosts and
mobile viewers share one websocket; vibecoding and notifications ride it as
channel tenants. No DB needed.

Run: python scripts/test_vibecoding_ws.py
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.auth.jwt import create_access_token

# Stub modules that build a MySQL engine (or DB deps) at import time.
deps = types.ModuleType("core.auth.dependencies")
deps.get_current_user = lambda: {"id": 1}
sys.modules["core.auth.dependencies"] = deps

dbsession = types.ModuleType("core.database.session")
async def _get_db():
    yield None
dbsession.get_db = _get_db
dbsession.async_session = None
dbsession.engine = None
sys.modules["core.database.session"] = dbsession

from core.wschannel import router as host_channel_router
from plugins.vibecoding.backend.router import router as vibe_router, register_host_channel
from plugins.notifications.backend.router import router as notif_router, notify_user

register_host_channel()

app = FastAPI()
app.include_router(host_channel_router)
app.include_router(vibe_router)
app.include_router(notif_router)

token = create_access_token({"sub": "1"})
client = TestClient(app)

# 1. auth rejected without token
try:
    with client.websocket_connect("/ws/host?device_id=d1") as ws:
        ws.receive_json()
    print("FAIL: unauthenticated host connection was accepted")
    sys.exit(1)
except Exception:
    print("PASS: no-token host connection rejected")

# 2. legacy endpoints are gone
for legacy in ("/ws/notifications", "/ws/vibecoding"):
    try:
        with client.websocket_connect(f"{legacy}?token={token}") as ws:
            ws.receive_json()
        print(f"FAIL: legacy endpoint {legacy} still accepting connections")
        sys.exit(1)
    except Exception:
        print(f"PASS: legacy endpoint {legacy} removed")

with client.websocket_connect(
    f"/ws/host?token={token}&role=desktop&device_id=dev-1&device_name=TestPC"
) as host:
    with client.websocket_connect(f"/ws/host?token={token}&role=viewer") as viewer:
        # viewer gets vibecoding snapshots on connect (viewer_connect hook)
        st = viewer.receive_json()
        assert st["channel"] == "vibecoding" and st["type"] == "device.status", st
        assert st["devices"][0]["device_id"] == "dev-1" and st["devices"][0]["name"] == "TestPC", st
        snap = viewer.receive_json()
        assert snap["channel"] == "vibecoding" and snap["type"] == "tasks.snapshot", snap
        print("PASS: viewer sees host device + task snapshot on connect")

        # 3. host -> task.event -> viewer (channel-wrapped)
        host.send_json({
            "channel": "vibecoding",
            "type": "task.event", "task_id": "t-1", "event": "started",
            "data": {"tool": "opencode", "project": "E:/repo", "project_name": "repo",
                     "input": "fix bug", "source": "mobile"},
            "ts": 123,
        })
        ev = viewer.receive_json()
        assert ev["channel"] == "vibecoding" and ev["type"] == "task.event", ev
        assert ev["device_id"] == "dev-1" and ev["task_id"] == "t-1", ev
        st = viewer.receive_json()
        assert st["type"] == "device.status" and st["devices"][0]["active_task"] == "t-1", st
        print("PASS: task.event relayed host -> viewer")

        # 4. viewer -> task.dispatch -> host receives channel-wrapped dispatch
        viewer.send_json({
            "channel": "vibecoding",
            "type": "task.dispatch", "task_id": "t-2", "tool": "claude",
            "project": "E:/repo", "input": "hello",
        })
        d = host.receive_json()
        assert d["channel"] == "vibecoding" and d["type"] == "task.dispatch", d
        assert d["task_id"] == "t-2" and d["source"] == "mobile", d
        print("PASS: task.dispatch routed viewer -> host (channel-wrapped)")

        # 5. projects.request / projects.response roundtrip (viewer <-> host)
        viewer.send_json({"channel": "vibecoding", "type": "projects.request", "request_id": "r1"})
        pr = host.receive_json()
        assert pr["channel"] == "vibecoding" and pr["type"] == "projects.request", pr
        host.send_json({
            "channel": "vibecoding",
            "type": "projects.response", "request_id": "r1",
            "projects": [{"name": "repo", "path": "E:/repo", "type": "node"}],
            "tools": {"opencode": True},
        })
        resp = viewer.receive_json()
        assert resp["channel"] == "vibecoding" and resp["type"] == "projects.response", resp
        assert resp["projects"][0]["name"] == "repo", resp
        print("PASS: projects.request/response roundtrip on the shared channel")

        # 6. done event -> viewer + registry
        host.send_json({
            "channel": "vibecoding",
            "type": "task.event", "task_id": "t-1", "event": "done",
            "data": {"code": 0, "duration_ms": 500, "output": "fixed"}, "ts": 456,
        })
        ev = viewer.receive_json()
        assert ev["type"] == "task.event" and ev["event"] == "done", ev
        st = viewer.receive_json()
        assert st["type"] == "device.status", st

        # 7. notifications fan out to BOTH the host and the viewer, channel-wrapped
        import asyncio

        async def fanout():
            await notify_user(1, {"title": "重要邮件", "body": "hello"})

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(fanout())
        finally:
            loop.close()
        via_host = host.receive_json()
        assert via_host["channel"] == "notifications" and via_host["title"] == "重要邮件", via_host
        via_viewer = viewer.receive_json()
        assert via_viewer["channel"] == "notifications" and via_viewer["title"] == "重要邮件", via_viewer
        print("PASS: notifications fan out to host + viewer, channel-wrapped")

rest = TestClient(app).get(
    "/api/vibecoding/tasks",
    headers={"Authorization": f"Bearer {token}"},
)
assert rest.status_code == 200, rest.text
tasks = rest.json()["tasks"]
assert any(t["task_id"] == "t-1" and t["status"] == "done" and t["output"] == "fixed" for t in tasks), tasks
print("PASS: REST /api/vibecoding/tasks reflects relayed events")

devs = TestClient(app).get(
    "/api/vibecoding/devices",
    headers={"Authorization": f"Bearer {token}"},
)
assert devs.status_code == 200 and devs.json()["devices"] == [], devs.json()
print("PASS: REST devices empty after host disconnect")

print("ALL SMOKE TESTS PASSED")
