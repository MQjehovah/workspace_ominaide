"""Smoke test for the shared host channel (`/ws/host`) and the vibecoding
protocol riding on it. No DB needed.

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
from plugins.vibecoding.backend.router import router as vibe_router, ws_router as vibe_ws_router, register_host_channel
from plugins.notifications.backend.router import router as notif_router, ws_router as notif_ws_router, ws_manager

register_host_channel()

app = FastAPI()
app.include_router(host_channel_router)
app.include_router(vibe_router)
app.include_router(vibe_ws_router)
app.include_router(notif_router)
app.include_router(notif_ws_router)

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

with client.websocket_connect(
    f"/ws/host?token={token}&device_id=dev-1&device_name=TestPC"
) as host:
    with client.websocket_connect(f"/ws/vibecoding?token={token}") as mobile:
        status = mobile.receive_json()
        assert status["type"] == "device.status", status
        assert status["devices"][0]["device_id"] == "dev-1", status
        assert status["devices"][0]["name"] == "TestPC", status
        snap = mobile.receive_json()
        assert snap["type"] == "tasks.snapshot", snap
        print("PASS: mobile sees host device on host connect")

        # 2. host -> task.event (channel-wrapped) -> relayed to mobile
        host.send_json({
            "channel": "vibecoding",
            "type": "task.event", "task_id": "t-1", "event": "started",
            "data": {"tool": "opencode", "project": "E:/repo", "project_name": "repo",
                     "input": "fix bug", "source": "mobile"},
            "ts": 123,
        })
        ev = mobile.receive_json()
        assert ev["type"] == "task.event" and ev["device_id"] == "dev-1" and ev["task_id"] == "t-1", ev
        st = mobile.receive_json()
        assert st["type"] == "device.status" and st["devices"][0]["active_task"] == "t-1", st
        print("PASS: task.event relayed host -> mobile")

        # 3. mobile -> task.dispatch -> host receives channel-wrapped dispatch
        mobile.send_json({
            "type": "task.dispatch", "task_id": "t-2", "tool": "claude",
            "project": "E:/repo", "input": "hello",
        })
        d = host.receive_json()
        assert d["channel"] == "vibecoding" and d["type"] == "task.dispatch", d
        assert d["task_id"] == "t-2" and d["source"] == "mobile", d
        print("PASS: task.dispatch routed mobile -> host (channel-wrapped)")

        # 4. projects.request / projects.response roundtrip
        mobile.send_json({"type": "projects.request", "request_id": "r1"})
        pr = host.receive_json()
        assert pr["channel"] == "vibecoding" and pr["type"] == "projects.request", pr
        host.send_json({
            "channel": "vibecoding",
            "type": "projects.response", "request_id": "r1",
            "projects": [{"name": "repo", "path": "E:/repo", "type": "node"}],
            "tools": {"opencode": True},
        })
        resp = mobile.receive_json()
        assert resp["type"] == "projects.response" and resp["projects"][0]["name"] == "repo", resp
        print("PASS: projects.request/response roundtrip via host channel")

        # 5. done event -> mobile + registry
        host.send_json({
            "channel": "vibecoding",
            "type": "task.event", "task_id": "t-1", "event": "done",
            "data": {"code": 0, "duration_ms": 500, "output": "fixed"}, "ts": 456,
        })
        ev = mobile.receive_json()
        assert ev["type"] == "task.event" and ev["event"] == "done", ev

        # 6. notifications fan out to BOTH legacy /ws/notifications and /ws/host
        with client.websocket_connect(f"/ws/notifications?token={token}") as legacy_mobile:
            import asyncio

            async def fanout():
                await ws_manager.notify_user(1, {"title": "重要邮件", "body": "hello"})

            new_loop = asyncio.new_event_loop()
            try:
                new_loop.run_until_complete(fanout())
            finally:
                new_loop.close()
            legacy = legacy_mobile.receive_json()
            assert legacy["title"] == "重要邮件", legacy
            via_host = host.receive_json()
            assert via_host["channel"] == "notifications" and via_host["title"] == "重要邮件", via_host
            print("PASS: notifications fan out to legacy ws and host channel")

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
