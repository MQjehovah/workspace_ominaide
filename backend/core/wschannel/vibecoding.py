"""Relay between thin clients (mobile) and desktop vibecoding plugins.

Channel: ``vibecoding``

The desktop plugin owns the OpenCode/Claude/Codex processes and the local
OpenCode server. The backend stays stateless apart from a short-lived routing
table and a small task ring buffer used for cold-start replay.

Message directions
------------------
viewer -> machine
    ``task.dispatch`` / ``task.control`` / ``projects.request``
    ``oc.request``  (list sessions, history, prompt, interrupt, ...)
machine -> viewer
    ``task.event`` / ``projects.response``
    ``oc.response`` (reply to a specific ``request_id``)
    ``oc.event``    (streamed OpenCode session events)
    ``device.status``
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from core.logging import get_logger
from core.wschannel.hub import host_channel

log = get_logger(__name__)

CHANNEL = "vibecoding"

# request_id -> (expires_at, user_id, viewer_websocket)
_pending: dict[str, tuple[float, int, Any]] = {}
PENDING_TTL_SECONDS = 180

# task_id -> machine_id, used to route controls when the caller omits it.
_task_machine: dict[str, str] = {}

# Newest-last ring buffer of task summaries for cold start replay.
_tasks: deque[dict] = deque(maxlen=200)
MAX_TASK_OUTPUT = 20_000

_TASK_FIELDS = (
    "task_id",
    "machine_id",
    "tool",
    "project",
    "project_name",
    "source",
    "input",
    "status",
    "started_ts",
    "ended_ts",
    "duration_ms",
    "code",
    "output",
    "error",
)


def register_channel() -> None:
    """Register the relay handler (idempotent)."""
    host_channel.register(
        CHANNEL,
        _handle_message,
        on_connect=_on_machine_connect,
        on_disconnect=_on_machine_disconnect,
        on_viewer_connect=_on_viewer_connect,
    )


# -- machine status ---------------------------------------------------------


def _machine_rows(user_id: int) -> list[dict]:
    rows = []
    for machine_id in host_channel.machine_ids(user_id):
        rows.append(
            {
                "machine_id": machine_id,
                "device_id": machine_id,
                "name": host_channel.machine_name(machine_id),
                "connected": True,
                "online": True,
                "platform": "desktop",
            }
        )
    return rows


async def _on_machine_connect(user_id: int, machine_id: str) -> None:
    await _push_machine_status(user_id)


async def _on_machine_disconnect(user_id: int, machine_id: str) -> None:
    for task_id, owner in list(_task_machine.items()):
        if owner == machine_id:
            _task_machine.pop(task_id, None)
    await _push_machine_status(user_id)


async def _on_viewer_connect(user_id: int, ws) -> None:
    await host_channel.send_to_ws(
        ws, CHANNEL, {"type": "device.status", "machines": _machine_rows(user_id)}
    )
    if _tasks:
        await host_channel.send_to_ws(
            ws,
            CHANNEL,
            {"type": "tasks.snapshot", "tasks": [_task_public(t) for t in _tasks][-50:]},
        )


async def _push_machine_status(user_id: int) -> None:
    await host_channel.broadcast_to_viewers(
        user_id, CHANNEL, {"type": "device.status", "machines": _machine_rows(user_id)}
    )


# -- task replay buffer -----------------------------------------------------


def _task_public(task: dict) -> dict:
    return {key: task[key] for key in _TASK_FIELDS if key in task}


def recent_tasks(limit: int = 50) -> list[dict]:
    items = list(_tasks)[-max(1, min(limit, 200)):]
    return [_task_public(task) for task in reversed(items)]


def _remember_task(payload: dict) -> None:
    task_id = str(payload.get("task_id") or "")
    if not task_id:
        return
    event = str(payload.get("event") or "")
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    now = int(time.time() * 1000)
    task = next((t for t in _tasks if t.get("task_id") == task_id), None)
    if task is None:
        task = {"task_id": task_id, "status": "pending", "started_ts": payload.get("ts") or now}
        _tasks.append(task)
    if payload.get("machine_id"):
        task["machine_id"] = payload["machine_id"]
        _task_machine[task_id] = str(payload["machine_id"])
    for key in ("tool", "project", "project_name", "source", "input"):
        if data.get(key) is not None:
            task[key] = data[key]
    if event == "started":
        task["status"] = "running"
        task["started_ts"] = payload.get("ts") or now
    elif event == "done":
        task["status"] = "done"
        task["ended_ts"] = payload.get("ts") or now
        task["duration_ms"] = data.get("duration_ms")
        task["code"] = data.get("code")
        output = str(data.get("output") or "")
        if output:
            task["output"] = output[-MAX_TASK_OUTPUT:]
        _task_machine.pop(task_id, None)
    elif event == "failed":
        task["status"] = "failed"
        task["ended_ts"] = payload.get("ts") or now
        task["duration_ms"] = data.get("duration_ms")
        task["code"] = data.get("code")
        task["error"] = data.get("error")
        _task_machine.pop(task_id, None)
    elif event == "milestone" and data.get("stage") == "cancelled":
        task["status"] = "cancelled"
        task["ended_ts"] = payload.get("ts") or now
        _task_machine.pop(task_id, None)


# -- routing ----------------------------------------------------------------


def _cleanup_pending() -> None:
    now = time.monotonic()
    for request_id, (expires_at, _, _) in list(_pending.items()):
        if expires_at <= now:
            _pending.pop(request_id, None)


async def _reply_error(ws, payload: dict, error: str) -> None:
    message_type = str(payload.get("type") or "")
    if message_type == "task.dispatch":
        message = {
            "type": "dispatch.error",
            "task_id": payload.get("task_id"),
            "reason": error,
            "machine_id": payload.get("machine_id"),
        }
    elif message_type == "projects.request":
        message = {
            "type": "projects.response",
            "request_id": payload.get("request_id"),
            "projects": [],
            "tools": {},
            "error": error,
            "machine_id": payload.get("machine_id"),
        }
    else:
        message = {
            "type": "oc.response",
            "ok": False,
            "action": payload.get("action"),
            "request_id": payload.get("request_id"),
            "error": error,
            "machine_id": payload.get("machine_id"),
        }
    await host_channel.send_to_ws(ws, CHANNEL, message)


async def _handle_message(user_id: int, machine_id: str, payload: dict, ws) -> None:
    message_type = str(payload.get("type") or "")

    # ---- desktop -> viewers ------------------------------------------------
    if machine_id:
        payload.setdefault("machine_id", machine_id)
        if message_type == "task.event":
            _remember_task(payload)
            await host_channel.broadcast_to_viewers(user_id, CHANNEL, payload)
            return
        if message_type in ("projects.response", "oc.response"):
            _cleanup_pending()
            request_id = str(payload.get("request_id") or "")
            pending = _pending.pop(request_id, None)
            if pending is not None:
                _, pending_user, pending_ws = pending
                if pending_user == user_id:
                    sent = await host_channel.send_to_ws(
                        pending_ws, CHANNEL, payload
                    )
                    if sent:
                        return
            await host_channel.broadcast_to_viewers(user_id, CHANNEL, payload)
            return
        if message_type in ("oc.event", "oc.sessions", "oc.machines"):
            await host_channel.broadcast_to_viewers(user_id, CHANNEL, payload)
            return
        return

    # ---- viewers -> desktop ------------------------------------------------
    if message_type == "task.dispatch":
        target = str(payload.get("machine_id") or "")
        if not target:
            sent = await host_channel.broadcast_to_machines(user_id, CHANNEL, payload)
            if not sent:
                await _reply_error(ws, payload, "没有在线的桌面设备，请先启动 OmniAide 桌面端")
            return
        if not await host_channel.send_to_machine(user_id, target, CHANNEL, payload):
            await _reply_error(ws, payload, "桌面设备不在线")
        return

    if message_type == "task.control":
        task_id = str(payload.get("task_id") or "")
        target = str(payload.get("machine_id") or "") or _task_machine.get(task_id, "")
        if target:
            await host_channel.send_to_machine(user_id, target, CHANNEL, payload)
        else:
            await host_channel.broadcast_to_machines(user_id, CHANNEL, payload)
        return

    if message_type == "projects.request":
        target = str(payload.get("machine_id") or "")
        request_id = str(payload.get("request_id") or "")
        if request_id:
            _cleanup_pending()
            _pending[request_id] = (time.monotonic() + PENDING_TTL_SECONDS, user_id, ws)
        if target:
            if not await host_channel.send_to_machine(user_id, target, CHANNEL, payload):
                await _reply_error(ws, payload, "桌面设备不在线")
        else:
            await host_channel.broadcast_to_machines(user_id, CHANNEL, payload)
        return

    if message_type == "oc.request":
        request_id = str(payload.get("request_id") or "")
        if request_id:
            _cleanup_pending()
            _pending[request_id] = (time.monotonic() + PENDING_TTL_SECONDS, user_id, ws)
        target = str(payload.get("machine_id") or "")
        if target:
            ok = await host_channel.send_to_machine(user_id, target, CHANNEL, payload)
        else:
            ok = bool(await host_channel.broadcast_to_machines(user_id, CHANNEL, payload))
        if not ok:
            _pending.pop(request_id, None)
            await _reply_error(ws, payload, "桌面设备不在线，请确认 OmniAide 已启动")
        return

    if message_type == "ping":
        await host_channel.send_to_ws(ws, CHANNEL, {"type": "pong"})
