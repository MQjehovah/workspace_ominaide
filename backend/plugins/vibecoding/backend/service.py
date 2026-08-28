import time
from collections import deque

from fastapi import WebSocket

from core.wschannel.hub import host_channel

CHANNEL = "vibecoding"


class VibecodingHub:
    """Vibecoding protocol as a tenant of the shared host channel.

    All transport (desktop hosts and mobile viewers alike) is delegated to
    `host_channel`. This hub owns only protocol semantics: the task registry
    (task_id -> device routing + recent-task ring buffer), relay between
    desktops and viewers, and the pending request/response map.
    """

    def __init__(self, history_max: int = 200):
        self.device_active_task: dict[str, str] = {}
        self.task_device: dict[str, str] = {}
        self._tasks: dict[int, dict] = {}
        self._task_order: dict[int, deque] = {}
        self._pending: dict[str, tuple] = {}
        self._history_max = history_max

    # -- host channel lifecycle ------------------------------------------

    def register(self):
        host_channel.register(
            CHANNEL,
            self.handle_message,
            on_connect=self._on_host_connected,
            on_disconnect=self._on_host_disconnected,
            on_viewer_connect=self._on_viewer_connected,
        )

    async def _on_host_connected(self, user_id: int, device_id: str):
        await self.push_device_status(user_id)

    async def _on_host_disconnected(self, user_id: int, device_id: str):
        self.device_active_task.pop(device_id, None)
        for tid, did in list(self.task_device.items()):
            if did == device_id:
                self.task_device.pop(tid, None)
        await self.push_device_status(user_id)

    async def _on_viewer_connected(self, user_id: int, ws: WebSocket):
        await host_channel.send_to_ws(ws, CHANNEL, {
            "type": "device.status", "devices": self.devices_payload(user_id),
        })
        await host_channel.send_to_ws(ws, CHANNEL, {
            "type": "tasks.snapshot", "tasks": self.recent_tasks(user_id, 50),
        })

    # -- registry views -----------------------------------------------------

    def devices_payload(self, user_id: int) -> list:
        return [
            {
                "device_id": device_id,
                "name": host_channel.device_name(device_id),
                "connected": True,
                "active_task": self.device_active_task.get(device_id),
            }
            for device_id in host_channel.device_ids(user_id)
        ]

    def desktop_ids(self, user_id: int) -> list:
        return host_channel.device_ids(user_id)

    async def push_device_status(self, user_id: int):
        await host_channel.broadcast_to_viewers(
            user_id, CHANNEL, {"type": "device.status", "devices": self.devices_payload(user_id)}
        )

    # -- protocol handler (both directions, channel: vibecoding) -------------

    async def handle_message(self, user_id: int, device_id: str, msg: dict, ws: WebSocket):
        msg_type = msg.get("type")
        if msg_type == "task.event":
            # desktop -> viewers
            if not device_id:
                return
            self.note_task_event(user_id, device_id, msg)
            event = {k: msg[k] for k in ("task_id", "event", "data", "ts") if k in msg}
            await host_channel.broadcast_to_viewers(
                user_id, CHANNEL, {"type": "task.event", "device_id": device_id, **event}
            )
            if msg.get("event") in ("started", "done", "failed"):
                await self.push_device_status(user_id)
        elif msg_type == "projects.response":
            # desktop -> the requesting viewer
            requester = self.pop_pending(msg.get("request_id") or "")
            if requester is not None:
                await host_channel.send_to_ws(requester, CHANNEL, msg)
        elif msg_type == "task.dispatch":
            dispatch = {
                "type": "task.dispatch",
                "task_id": msg.get("task_id"),
                "tool": msg.get("tool"),
                "project": msg.get("project"),
                "input": msg.get("input"),
                "source": "mobile",
            }
            target = msg.get("device_id")
            if target:
                if not await host_channel.send_to_host(user_id, target, CHANNEL, dispatch):
                    await self._dispatch_error(user_id, msg.get("task_id"), "目标设备不在线")
            else:
                sent = await host_channel.broadcast_to_hosts(user_id, CHANNEL, dispatch)
                if not sent:
                    await self._dispatch_error(user_id, msg.get("task_id"), "没有在线的桌面设备")
        elif msg_type == "task.control":
            control = {
                "type": "task.control",
                "task_id": msg.get("task_id"),
                "action": msg.get("action", "cancel"),
            }
            target = self.task_device.get(msg.get("task_id") or "")
            if target:
                await host_channel.send_to_host(user_id, target, CHANNEL, control)
            else:
                await host_channel.broadcast_to_hosts(user_id, CHANNEL, control)
        elif msg_type == "projects.request":
            request_id = msg.get("request_id") or ""
            self.register_pending(request_id, ws)
            request = {"type": "projects.request", "request_id": request_id}
            target = msg.get("device_id")
            if target:
                await host_channel.send_to_host(user_id, target, CHANNEL, request)
            else:
                await host_channel.broadcast_to_hosts(user_id, CHANNEL, request)

    async def _dispatch_error(self, user_id: int, task_id, reason: str):
        await host_channel.broadcast_to_viewers(user_id, CHANNEL, {
            "type": "dispatch.error", "task_id": task_id, "reason": reason,
        })

    # -- task registry ------------------------------------------------------

    def note_task_event(self, user_id: int, device_id: str, msg: dict):
        task_id = msg.get("task_id")
        event = msg.get("event")
        data = msg.get("data") or {}
        if not task_id or not event:
            return
        if event == "started":
            self.task_device[task_id] = device_id
            self.device_active_task[device_id] = task_id
            tasks = self._tasks.setdefault(user_id, {})
            if task_id not in tasks:
                order = self._task_order.setdefault(user_id, deque(maxlen=self._history_max))
                order.append(task_id)
            tasks[task_id] = {
                "task_id": task_id,
                "device_id": device_id,
                "tool": data.get("tool"),
                "project": data.get("project"),
                "project_name": data.get("project_name"),
                "source": data.get("source"),
                "input": (data.get("input") or "")[:300],
                "status": "running",
                "started_ts": msg.get("ts") or int(time.time() * 1000),
                "ended_ts": None,
                "duration_ms": None,
                "code": None,
                "output": "",
                "error": None,
            }
            while len(tasks) > self._history_max * 2:
                tasks.pop(next(iter(tasks)), None)
        elif event == "done":
            self._finish_task(user_id, task_id, "done", code=data.get("code"),
                              duration_ms=data.get("duration_ms"), output=data.get("output"))
        elif event == "failed":
            self._finish_task(user_id, task_id, "failed", code=data.get("code"),
                              duration_ms=data.get("duration_ms"), error=data.get("error"))
        elif event == "milestone" and data.get("stage") == "cancelled":
            self._finish_task(user_id, task_id, "cancelled")

    def _finish_task(self, user_id: int, task_id: str, status: str,
                     code=None, duration_ms=None, output=None, error=None):
        task = (self._tasks.get(user_id) or {}).get(task_id)
        if not task:
            return
        task["status"] = status
        task["ended_ts"] = int(time.time() * 1000)
        if duration_ms is not None:
            task["duration_ms"] = duration_ms
        if code is not None:
            task["code"] = code
        if output:
            task["output"] = str(output)[:20000]
        if error is not None:
            task["error"] = str(error)[:2000]
        device_id = self.task_device.get(task_id)
        if device_id and self.device_active_task.get(device_id) == task_id:
            self.device_active_task.pop(device_id, None)

    def recent_tasks(self, user_id: int, limit: int = 50) -> list:
        order = self._task_order.get(user_id) or deque()
        tasks = self._tasks.get(user_id) or {}
        out = []
        for tid in reversed(order):
            task = tasks.get(tid)
            if task:
                out.append(task)
            if len(out) >= max(1, min(limit, 200)):
                break
        return out

    # -- viewer -> desktop request/response ----------------------------------

    def register_pending(self, request_id: str, ws):
        if request_id and ws is not None:
            self._pending[request_id] = (ws, time.time())

    def pop_pending(self, request_id: str):
        entry = self._pending.pop(request_id, None) if request_id else None
        if time.time() - (entry[1] if entry else 0) > 15:
            return None
        return entry[0] if entry else None


hub = VibecodingHub()
