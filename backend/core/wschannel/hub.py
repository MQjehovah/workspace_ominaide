import logging
from typing import Callable, Optional

from fastapi import WebSocket

log = logging.getLogger("uvicorn")


class HostChannelHub:
    """The single multiplexed WebSocket channel for all clients.

    Two connection roles on `/ws/host`:
    - hosts (role=desktop): an OmniAide desktop device with a stable device_id.
      Send channel-tagged messages upstream; receive channel-routed messages
      for the desktop plugin that subscribed to that channel.
    - viewers (role=viewer): thin clients (mobile etc.) that receive
      channel-tagged broadcasts and may also send channel-tagged commands.

    Backend plugins register per-channel handlers; every message on the wire
    (both directions) carries a `channel` namespace.
    """

    def __init__(self):
        self.hosts: dict[int, dict[str, WebSocket]] = {}
        self.viewers: dict[int, set] = {}
        self.device_names: dict[str, str] = {}
        self._handlers: dict[str, Callable] = {}
        self._connect_hooks: dict[str, list] = {}
        self._disconnect_hooks: dict[str, list] = {}
        self._viewer_connect_hooks: dict[str, list] = {}

    def register(self, channel: str, on_message: Callable,
                 on_connect: Optional[Callable] = None,
                 on_disconnect: Optional[Callable] = None,
                 on_viewer_connect: Optional[Callable] = None):
        self._handlers[channel] = on_message
        if on_connect is not None:
            self._connect_hooks.setdefault(channel, []).append(on_connect)
        if on_disconnect is not None:
            self._disconnect_hooks.setdefault(channel, []).append(on_disconnect)
        if on_viewer_connect is not None:
            self._viewer_connect_hooks.setdefault(channel, []).append(on_viewer_connect)

    # -- host (desktop) connections ----------------------------------------

    async def connect_host(self, user_id: int, device_id: str, name: str, ws: WebSocket):
        self.hosts.setdefault(user_id, {})[device_id] = ws
        self.device_names[device_id] = name or device_id
        for hooks in self._connect_hooks.values():
            for hook in hooks:
                try:
                    await hook(user_id, device_id)
                except Exception:
                    log.exception("[wschannel] connect hook error")

    async def disconnect_host(self, user_id: int, device_id: str):
        conns = self.hosts.get(user_id)
        if conns is not None:
            conns.pop(device_id, None)
            if not conns:
                self.hosts.pop(user_id, None)
        self.device_names.pop(device_id, None)
        for hooks in self._disconnect_hooks.values():
            for hook in hooks:
                try:
                    await hook(user_id, device_id)
                except Exception:
                    log.exception("[wschannel] disconnect hook error")

    # -- viewer (mobile etc.) connections ------------------------------------

    async def connect_viewer(self, user_id: int, ws: WebSocket):
        self.viewers.setdefault(user_id, set()).add(ws)
        for hooks in self._viewer_connect_hooks.values():
            for hook in hooks:
                try:
                    await hook(user_id, ws)
                except Exception:
                    log.exception("[wschannel] viewer-connect hook error")

    def disconnect_viewer(self, user_id: int, ws: WebSocket):
        conns = self.viewers.get(user_id)
        if conns is not None:
            conns.discard(ws)
            if not conns:
                self.viewers.pop(user_id, None)

    # -- connectivity queries -------------------------------------------------

    def device_ids(self, user_id: int) -> list:
        return list((self.hosts.get(user_id) or {}).keys())

    def device_name(self, device_id: str) -> str:
        return self.device_names.get(device_id, device_id)

    # -- sends (all outbound messages are channel-wrapped) ---------------------

    async def _send_ws(self, ws: WebSocket, channel: str, data: dict) -> bool:
        try:
            await ws.send_json({"channel": channel, **data})
            return True
        except Exception:
            return False

    async def send_to_host(self, user_id: int, device_id: str, channel: str, data: dict) -> bool:
        ws = (self.hosts.get(user_id) or {}).get(device_id)
        if not ws:
            return False
        if not await self._send_ws(ws, channel, data):
            await self.disconnect_host(user_id, device_id)
            return False
        return True

    async def send_to_ws(self, ws: WebSocket, channel: str, data: dict) -> bool:
        return await self._send_ws(ws, channel, data)

    async def broadcast_to_hosts(self, user_id: int, channel: str, data: dict) -> int:
        sent = 0
        for device_id in self.device_ids(user_id):
            if await self.send_to_host(user_id, device_id, channel, data):
                sent += 1
        return sent

    async def broadcast_to_viewers(self, user_id: int, channel: str, data: dict) -> int:
        sent = 0
        for ws in list(self.viewers.get(user_id) or set()):
            if await self._send_ws(ws, channel, data):
                sent += 1
            else:
                self.disconnect_viewer(user_id, ws)
        return sent

    async def broadcast(self, user_id: int, channel: str, data: dict) -> int:
        sent = await self.broadcast_to_hosts(user_id, channel, data)
        sent += await self.broadcast_to_viewers(user_id, channel, data)
        return sent

    # -- upstream dispatch ------------------------------------------------------

    async def handle_message(self, user_id: int, device_id: str, msg: dict, ws: WebSocket) -> bool:
        channel = msg.get("channel")
        handler = self._handlers.get(channel)
        if not handler:
            return False
        payload = {k: v for k, v in msg.items() if k != "channel"}
        try:
            await handler(user_id, device_id, payload, ws)
        except Exception:
            log.exception(f"[wschannel] handler error channel={channel}")
        return True


host_channel = HostChannelHub()
