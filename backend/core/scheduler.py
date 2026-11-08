"""Core periodic job scheduler.

Plugins declare periodic jobs; core owns the clock, enqueueing and lifecycle.
Execution happens through ``core.jobs`` so retries, timeouts and run history
are shared with other background work.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from core.jobs.service import register_handler, enqueue
from core.logging import get_logger

log = get_logger(__name__)

CHECK_INTERVAL = 5.0


@dataclass
class PeriodicJob:
    key: str
    owner: str
    handler: Callable[[], Awaitable[object]]
    interval_seconds: int
    timeout_seconds: int = 300
    run_on_start: bool = False
    enabled: bool = True
    next_run_at: float = field(default=0.0)
    startup_pending: bool = field(default=False)


class Scheduler:
    def __init__(self) -> None:
        self._jobs: dict[str, PeriodicJob] = {}
        self._task: asyncio.Task | None = None
        self._boot_id = uuid.uuid4().hex[:12]

    def register(self, job: PeriodicJob) -> None:
        if job.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        job.next_run_at = 0.0 if job.run_on_start else time.time() + job.interval_seconds
        job.startup_pending = job.run_on_start
        self._jobs[job.key] = job
        log.info(
            f"[scheduler] registered {job.key} owner={job.owner} "
            f"interval={job.interval_seconds}s"
        )

    def unregister_owner(self, owner: str) -> None:
        for key in [k for k, j in self._jobs.items() if j.owner == owner]:
            self._jobs.pop(key, None)
            log.info(f"[scheduler] unregistered {key} owner={owner}")

    def get(self, key: str) -> PeriodicJob | None:
        return self._jobs.get(key)

    async def _enqueue_due(self, now: float) -> None:
        for job in list(self._jobs.values()):
            if not job.enabled or now < job.next_run_at:
                continue
            bucket = int(now // job.interval_seconds)
            job.next_run_at = (bucket + 1) * job.interval_seconds
            if job.startup_pending:
                # A restart should trigger the job even if this interval's
                # bucket already ran in a previous process.
                job.startup_pending = False
                idempotency_key = f"scheduler:{job.key}:startup:{self._boot_id}"
            else:
                idempotency_key = f"scheduler:{job.key}:{bucket}"
            try:
                await enqueue(
                    "scheduler.job",
                    {"key": job.key},
                    idempotency_key=idempotency_key,
                )
            except Exception as exc:
                log.warning(f"[scheduler] enqueue {job.key} failed: {exc}")

    async def _loop(self) -> None:
        while True:
            try:
                await self._enqueue_due(time.time())
            except Exception as exc:
                log.warning(f"[scheduler] loop error: {exc}")
            await asyncio.sleep(CHECK_INTERVAL)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


async def _run_scheduled(job) -> None:
    key = str((job.payload or {}).get("key") or "")
    spec = scheduler.get(key)
    if spec is None:
        return {"skipped": True, "reason": "job unregistered"}
    await asyncio.wait_for(spec.handler(), timeout=spec.timeout_seconds)
    return {"ok": True, "key": key}


scheduler = Scheduler()
register_handler("scheduler.job", _run_scheduled)
