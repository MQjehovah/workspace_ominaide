"""Realtime event bus for hardware devices.

Devices cannot easily hold a WebSocket on constrained firmware, so the device
plugin exposes a long-poll endpoint backed by this in-process bus. The bus
keeps a short replay window (so a reconnecting device does not miss events)
and wakes waiters immediately when a notification/reminder is published.

Every event is ``{"id": int, "type": str, "ts": int, ...payload}``. The
monotonic ``id`` is per-user and lets the device ask for "everything after N".
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Any


class DeviceEventBus:
    def __init__(self, replay: int = 50):
        self._events: dict[int, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=replay)
        )
        self._seq: dict[int, int] = defaultdict(int)
        self._waiters: dict[int, set[asyncio.Event]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def publish(self, user_id: int, kind: str, data: dict | None = None) -> dict:
        async with self._lock:
            self._seq[user_id] += 1
            event = {
                "id": self._seq[user_id],
                "type": kind,
                "ts": int(time.time()),
                **(data or {}),
            }
            self._events[user_id].append(event)
            waiters = list(self._waiters.get(user_id, ()))
        for waiter in waiters:
            waiter.set()
        return event

    def since(self, user_id: int, since_id: int) -> list[dict[str, Any]]:
        return [e for e in self._events.get(user_id, ()) if e["id"] > since_id]

    def last_id(self, user_id: int) -> int:
        return self._seq.get(user_id, 0)

    async def wait(
        self, user_id: int, since_id: int, timeout: float
    ) -> list[dict[str, Any]]:
        """Return immediately if events exist, otherwise wait up to timeout."""
        deadline = asyncio.get_running_loop().time() + max(0.0, timeout)
        while True:
            events = self.since(user_id, since_id)
            if events:
                return events
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return []
            waiter = asyncio.Event()
            self._waiters[user_id].add(waiter)
            try:
                await asyncio.wait_for(waiter.wait(), timeout=min(remaining, 25.0))
            except asyncio.TimeoutError:
                pass
            finally:
                self._waiters[user_id].discard(waiter)


device_events = DeviceEventBus()


async def publish_device_event(user_id: int, kind: str, data: dict | None = None) -> dict:
    return await device_events.publish(user_id, kind, data)
