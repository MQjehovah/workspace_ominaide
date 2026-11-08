"""Server-side bridge for tools that execute on a user's desktop computer.

The desktop app keeps an outbound WebSocket to ``/ws/host``. Calls are sent on
the ``local-tools`` channel and correlated by ``call_id``; the desktop replies
with a result. Nothing here opens an inbound port on the user's machine.
"""

from __future__ import annotations

import asyncio
import uuid

from core.logging import get_logger
from core.wschannel.hub import host_channel

log = get_logger(__name__)

CHANNEL = "local-tools"

_pending: dict[str, asyncio.Future] = {}


class LocalDeviceError(RuntimeError):
    pass


def register_channel() -> None:
    """Register the inbound result handler (idempotent)."""
    host_channel.register(CHANNEL, _handle_message)


async def _handle_message(user_id: int, device_id: str, payload: dict, ws) -> None:
    if payload.get("type") != "result":
        return
    call_id = str(payload.get("call_id") or "")
    future = _pending.get(call_id)
    if future is not None and not future.done():
        future.set_result(payload)


def devices(user_id: int) -> list[dict]:
    return [
        {
            "device_id": device_id,
            "name": host_channel.device_name(device_id),
        }
        for device_id in host_channel.device_ids(user_id)
    ]


def resolve_device(
    user_id: int,
    *,
    device_id: str | None = None,
    device: str | None = None,
) -> str:
    """Resolve a device by id or name. Requires a choice when several are online."""
    online = host_channel.device_ids(user_id)
    if not online:
        raise LocalDeviceError(
            "没有在线的桌面设备。请先打开 OmniAide 桌面端并登录。"
        )

    device_id = (device_id or "").strip()
    if device_id:
        if device_id in online:
            return device_id
        raise LocalDeviceError(f"桌面设备 {device_id} 不在线")

    name = (device or "").strip().lower()
    if name:
        matches = [
            item for item in online
            if host_channel.device_name(item).lower() == name
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise LocalDeviceError(f"找不到名为 {device} 的桌面设备")
        raise LocalDeviceError(
            f"有多个名为 {device} 的设备，请改用 device_id 指定"
        )

    if len(online) == 1:
        return online[0]

    labels = ", ".join(
        f"{host_channel.device_name(item)} ({item})" for item in online
    )
    raise LocalDeviceError(
        f"有多个桌面设备在线，请用 device_id 指定：{labels}"
    )


async def call_local(
    user_id: int,
    device_id: str,
    tool: str,
    args: dict,
    *,
    timeout_seconds: int = 600,
) -> dict:
    """Send a tool call to one desktop and wait for its result."""
    loop = asyncio.get_running_loop()
    call_id = uuid.uuid4().hex
    future: asyncio.Future = loop.create_future()
    _pending[call_id] = future
    try:
        sent = await host_channel.send_to_host(
            user_id,
            device_id,
            CHANNEL,
            {
                "type": "call",
                "call_id": call_id,
                "tool": tool,
                "args": args,
                "timeout_seconds": timeout_seconds,
            },
        )
        if not sent:
            raise LocalDeviceError("桌面设备已离线，或消息发送失败")
        # The desktop shows an approval dialog before running the command, so
        # leave extra room beyond the command timeout.
        return await asyncio.wait_for(future, timeout=timeout_seconds + 120)
    except asyncio.TimeoutError as exc:
        raise LocalDeviceError(f"本地执行超时（{timeout_seconds} 秒）") from exc
    finally:
        _pending.pop(call_id, None)
