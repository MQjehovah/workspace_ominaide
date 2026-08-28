import time
from collections import deque

from fastapi import WebSocket

from core.wschannel.hub import host_channel

CHANNEL = "vibecoding"


class VibecodingHub:
    """Vibecoding protocol on top of the shared host channel.

    Desktop-side connectivity is delegated entirely to `host_channel` (the
    host's single multiplexed websocket). This hub only owns the mobile viewer
    connections, the task registry (task_id -> device routing + recent-task
    ring buffer) and the pending request/response map.
    """

    def __init__(self, history_max: int = 200):
        self.mobiles: dict[int, set] = {}
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
            self.handle_desktop_message,
            on_connect=self._on_host_connected,
            on_disconnect=self._on_host_disconnected,
        )

    async def _on_host_connected(self, user_id: int, device_id: str):
        await self.broadcast_device_status(user_id)

    async def _on_host_disconnected(self, user_id: int, device_id: str):
        self.device_active_task.pop(device_id, None)
        for tid, did in list(self.task_device.items()):
            if did == device_id:
                self.task_device.pop(tid, None)
        await self.broadcast_device_status(user_id)

    # -- mobile connections -----------------------------------------------

    async def connect_mobile(self, user_id: int, ws: WebSocket):
        self.mobiles.setdefault(user_id, set()).add(ws)

    def disconnect_mobile(self, user_id: int, ws: WebSocket):
        conns = self.mobiles.get(user_id)
        if conns is not None:
            conns.discard(ws)
            if not conns:
                self.mobiles.pop(user_id, None)

    async def send_to_mobiles(self, user_id: int, data: dict):
        for ws in list(self.mobiles.get(user_id) or set()):
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect_mobile(user_id, ws)

    async def broadcast_device_status(self, user_id: int):
        await self.send_to_mobiles(
            user_id, {"type": "device.status", "devices": self.devices_payload(user_id)}
        )

    # -- desktop reachability via the host channel -------------------------

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

    async def send_to_desktop(self, user_id: int, device_id: str, data: dict) -> bool:
        return await host_channel.send(user_id, device_id, CHANNEL, data)

    async def broadcast_to_desktops(self, user_id: int, data: dict) -> int:
        return await host_channel.broadcast(user_id, CHANNEL, data)

    # -- desktop -> mobile relay (host channel handler) --------------------

    async def handle_desktop_message(self, user_id: int, device_id: str, msg: dict):
        msg_type = msg.get("type")
        if msg_type == "task.event":
            self.note_task_event(user_id, device_id, msg)
            event = {k: msg[k] for k in ("task_id", "event", "data", "ts") if k in msg}
            await self.send_to_mobiles(
                user_id, {"type": "task.event", "device_id": device_id, **event}
            )
            if msg.get("event") in ("started", "done", "failed"):
                await self.broadcast_device_status(user_id)
        elif msg_type == "projects.response":
            requester = self.pop_pending(msg.get("request_id") or "")
            if requester is not None:
                try:
                    await requester.send_json(msg)
                except Exception:
                    pass

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

    # -- mobile -> desktop request/response ---------------------------------

    def register_pending(self, request_id: str, ws: WebSocket):
        if request_id:
            self._pending[request_id] = (ws, time.time())

    def pop_pending(self, request_id: str):
        entry = self._pending.pop(request_id, None) if request_id else None
        if time.time() - (entry[1] if entry else 0) > 15:
            return None
        return entry[0] if entry else None


hub = VibecodingHub()
