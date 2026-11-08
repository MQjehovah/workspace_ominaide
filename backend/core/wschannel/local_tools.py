"""Server-side bridge for tools that execute on a user's desktop computer.

The desktop app keeps an outbound WebSocket to ``/ws/host``. Calls are sent on
the ``local-tools`` channel and correlated by ``call_id``; the desktop replies
with a result. Nothing here opens an inbound port on the user's machine.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from core.logging import get_logger
from core.wschannel.hub import host_channel

log = get_logger(__name__)

CHANNEL = "local-tools"

_pending: dict[str, asyncio.Future] = {}

MAX_JOB_EVENTS = 20_000
MAX_JOB_CHARS = 2_000_000
JOB_TTL_SECONDS = 3600


class LocalMachineError(RuntimeError):
    pass


@dataclass
class LocalJob:
    job_id: str
    user_id: int
    machine_id: str
    command: str
    cwd: str | None = None
    status: str = "starting"
    exit_code: int | None = None
    timed_out: bool = False
    cancelled: bool = False
    truncated: bool = False
    events: list[tuple[str, str]] = field(default_factory=list)
    total_chars: int = 0
    started_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None
    event: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def running(self) -> bool:
        return self.status in ("starting", "running", "cancelling")


_jobs: dict[str, LocalJob] = {}


def _cleanup_jobs() -> None:
    now = time.monotonic()
    stale = [
        job_id
        for job_id, job in _jobs.items()
        if not job.running
        and job.finished_at is not None
        and now - job.finished_at > JOB_TTL_SECONDS
    ]
    for job_id in stale:
        _jobs.pop(job_id, None)


def _append_job_event(job: LocalJob, stream: str, chunk: str) -> None:
    if not chunk or job.total_chars >= MAX_JOB_CHARS:
        job.truncated = True
        return
    remaining = MAX_JOB_CHARS - job.total_chars
    text = chunk[:remaining]
    job.events.append((stream, text))
    job.total_chars += len(text)
    if len(job.events) > MAX_JOB_EVENTS:
        job.events = job.events[-MAX_JOB_EVENTS:]
    if len(text) < len(chunk):
        job.truncated = True
    job.event.set()


def _get_job(user_id: int, job_id: str) -> LocalJob:
    job = _jobs.get(job_id)
    if job is None or job.user_id != user_id:
        raise LocalMachineError(f"找不到本地任务 {job_id}")
    return job


def register_channel() -> None:
    """Register the inbound result handler (idempotent)."""
    host_channel.register(CHANNEL, _handle_message, on_disconnect=_on_machine_disconnect)


async def _on_machine_disconnect(user_id: int, machine_id: str) -> None:
    for job in _jobs.values():
        if (
            job.user_id == user_id
            and job.machine_id == machine_id
            and job.running
        ):
            job.status = "failed"
            job.finished_at = time.monotonic()
            job.event.set()


async def _handle_message(user_id: int, machine_id: str, payload: dict, ws) -> None:
    message_type = payload.get("type")
    if message_type == "job_event":
        job = _jobs.get(str(payload.get("job_id") or ""))
        if job is None or job.user_id != user_id or job.machine_id != machine_id:
            return
        _append_job_event(
            job,
            str(payload.get("stream") or "stdout"),
            str(payload.get("chunk") or ""),
        )
        return
    if message_type == "job_done":
        job = _jobs.get(str(payload.get("job_id") or ""))
        if job is None or job.user_id != user_id or job.machine_id != machine_id:
            return
        job.status = "cancelled" if payload.get("cancelled") else "done"
        job.cancelled = bool(payload.get("cancelled"))
        job.timed_out = bool(payload.get("timed_out"))
        job.exit_code = payload.get("exit_code")
        job.finished_at = time.monotonic()
        job.event.set()
        return
    if message_type != "result":
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


async def start_job(
    user_id: int,
    machine_id: str,
    command: str,
    *,
    cwd: str | None = None,
    timeout_seconds: int = 600,
) -> LocalJob:
    """Start a long-running local command and return its job handle."""
    _cleanup_jobs()
    job_id = uuid.uuid4().hex
    job = LocalJob(
        job_id=job_id,
        user_id=user_id,
        machine_id=machine_id,
        command=command,
        cwd=cwd,
    )
    _jobs[job_id] = job
    try:
        response = await call_local(
            user_id,
            machine_id,
            "shell_start",
            {
                "job_id": job_id,
                "command": command,
                "cwd": cwd,
                "timeout_seconds": timeout_seconds,
            },
            timeout_seconds=120,
        )
    except Exception:
        _jobs.pop(job_id, None)
        raise
    if not response.get("ok"):
        _jobs.pop(job_id, None)
        raise LocalMachineError(str(response.get("error") or "启动失败"))
    result = response.get("result") or {}
    job.cwd = str(result.get("cwd") or cwd or "")
    if job.status == "starting":
        job.status = "running"
    return job


async def wait_job(
    user_id: int,
    job_id: str,
    *,
    cursor: int = 0,
    wait_seconds: int = 20,
) -> tuple[LocalJob, list[tuple[str, str]], int]:
    """Return output events after ``cursor`` and the next cursor."""
    job = _get_job(user_id, job_id)
    cursor = max(0, int(cursor))
    wait_seconds = min(max(int(wait_seconds), 1), 300)
    deadline = time.monotonic() + wait_seconds
    while len(job.events) <= cursor and job.running:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        job.event.clear()
        # Re-check after clear to avoid missing a chunk set just before it.
        if len(job.events) > cursor or not job.running:
            break
        try:
            await asyncio.wait_for(job.event.wait(), timeout=remaining)
        except asyncio.TimeoutError:
            break
    events = job.events[cursor:]
    return job, events, len(job.events)


async def cancel_job(user_id: int, job_id: str) -> LocalJob:
    job = _get_job(user_id, job_id)
    if not job.running:
        return job
    job.status = "cancelling"
    job.event.set()
    try:
        await call_local(
            user_id,
            job.machine_id,
            "shell_cancel",
            {"job_id": job_id},
            timeout_seconds=30,
        )
    except Exception as exc:
        log.warning(f"[local] cancel {job_id} failed: {exc}")
    return job
