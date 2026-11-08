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


class LocalMachineError(RuntimeError):
    pass


def register_channel() -> None:
    """Register the inbound result handler (idempotent)."""
    host_channel.register(CHANNEL, _handle_message)


async def _handle_message(user_id: int, machine_id: str, payload: dict, ws) -> None:
    if payload.get("type") != "result":
        return
    call_id = str(payload.get("call_id") or "")
    future = _pending.get(call_id)
    if future is not None and not future.done():
        future.set_result(payload)


def machines(user_id: int) -> list[dict]:
    return [
        {
            "machine_id": machine_id,
            "name": host_channel.machine_name(machine_id),
        }
        for machine_id in host_channel.machine_ids(user_id)
    ]


def resolve_machine(
    user_id: int,
    *,
    machine_id: str | None = None,
    machine: str | None = None,
) -> str:
    """Resolve a local computer by id or name. Requires a choice when several are online."""
    online = host_channel.machine_ids(user_id)
    if not online:
        raise LocalMachineError(
            "没有在线的本地机器。请先打开 OmniAide 桌面端并登录。"
        )

    machine_id = (machine_id or "").strip()
    if machine_id:
        if machine_id in online:
            return machine_id
        raise LocalMachineError(f"本地机器 {machine_id} 不在线")

    name = (machine or "").strip().lower()
    if name:
        matches = [
            item for item in online
            if host_channel.machine_name(item).lower() == name
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise LocalMachineError(f"找不到名为 {machine} 的本地机器")
        raise LocalMachineError(
            f"有多个名为 {machine} 的本地机器，请改用 machine_id 指定"
        )

    if len(online) == 1:
        return online[0]

    labels = ", ".join(
        f"{host_channel.machine_name(item)} ({item})" for item in online
    )
    raise LocalMachineError(
        f"有多个本地机器在线，请用 machine_id 指定：{labels}"
    )


async def call_local(
    user_id: int,
    machine_id: str,
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
        sent = await host_channel.send_to_machine(
            user_id,
            machine_id,
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
            raise LocalMachineError("本地机器已离线，或消息发送失败")
        # The desktop shows an approval dialog before running the command, so
        # leave extra room beyond the command timeout.
        return await asyncio.wait_for(future, timeout=timeout_seconds + 120)
    except asyncio.TimeoutError as exc:
        raise LocalMachineError(f"本地执行超时（{timeout_seconds} 秒）") from exc
    finally:
        _pending.pop(call_id, None)
