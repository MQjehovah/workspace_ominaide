import logging
from typing import Callable, Optional

from fastapi import WebSocket

log = logging.getLogger("uvicorn")


class HostChannelHub:
    """Generic multiplexed WebSocket channel for desktop hosts.

    One websocket per host device (`/ws/host`). Every message carries a
    `channel` namespace; backend plugins register handlers per channel and
    parse/dispatch their own protocol. Outbound messages to a host are always
    wrapped with the sender's channel name so the host can route them to the
    owning plugin.
    """

    def __init__(self):
        self.hosts: dict[int, dict[str, WebSocket]] = {}
        self.device_names: dict[str, str] = {}
        self._handlers: dict[str, Callable] = {}
        self._connect_hooks: dict[str, list] = {}
        self._disconnect_hooks: dict[str, list] = {}

    def register(self, channel: str, on_message: Callable,
                 on_connect: Optional[Callable] = None,
                 on_disconnect: Optional[Callable] = None):
        self._handlers[channel] = on_message
        if on_connect is not None:
            self._connect_hooks.setdefault(channel, []).append(on_connect)
        if on_disconnect is not None:
            self._disconnect_hooks.setdefault(channel, []).append(on_disconnect)

    async def connect(self, user_id: int, device_id: str, name: str, ws: WebSocket):
        self.hosts.setdefault(user_id, {})[device_id] = ws
        self.device_names[device_id] = name or device_id
        for hooks in self._connect_hooks.values():
            for hook in hooks:
                try:
                    await hook(user_id, device_id)
                except Exception:
                    log.exception("[wschannel] connect hook error")

    async def disconnect(self, user_id: int, device_id: str):
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

    def device_ids(self, user_id: int) -> list:
        return list((self.hosts.get(user_id) or {}).keys())

    def device_name(self, device_id: str) -> str:
        return self.device_names.get(device_id, device_id)

    async def send(self, user_id: int, device_id: str, channel: str, data: dict) -> bool:
        ws = (self.hosts.get(user_id) or {}).get(device_id)
        if not ws:
            return False
        try:
            await ws.send_json({"channel": channel, **data})
            return True
        except Exception:
            await self.disconnect(user_id, device_id)
            return False

    async def broadcast(self, user_id: int, channel: str, data: dict) -> int:
        sent = 0
        for device_id in self.device_ids(user_id):
            if await self.send(user_id, device_id, channel, data):
                sent += 1
        return sent

    async def handle_message(self, user_id: int, device_id: str, msg: dict) -> bool:
        channel = msg.get("channel")
        handler = self._handlers.get(channel)
        if not handler:
            return False
        payload = {k: v for k, v in msg.items() if k != "channel"}
        try:
            await handler(user_id, device_id, payload)
        except Exception:
            log.exception(f"[wschannel] handler error channel={channel}")
        return True


host_channel = HostChannelHub()
