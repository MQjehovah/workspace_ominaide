"""Idle workspace reaper and simple lifecycle reconciliation."""

from __future__ import annotations

import asyncio
import time

from app.docker_client import SandboxDocker
from app.store import WorkspaceStore


async def reaper_loop(
    store: WorkspaceStore,
    docker: SandboxDocker | None,
    *,
    interval: int,
    log,
) -> None:
    while True:
        await asyncio.sleep(max(interval, 5))
        if docker is None:
            continue
        try:
            await _tick(store, docker, log)
        except Exception as exc:  # keep the reaper alive
            log.warning("sandbox reaper tick failed: %s", exc)


async def _tick(store: WorkspaceStore, docker: SandboxDocker, log) -> None:
    now = time.time()
    for workspace in store.list():
        if not workspace.container_id:
            if workspace.status in ("creating", "preparing") and now - workspace.created_at > 900:
                store.update(workspace.id, status="error", error="container was never created")
            continue

        docker_status = await asyncio.to_thread(docker.status, workspace.container_id)
        if docker_status == "missing":
            store.update(workspace.id, status="error", error="container is missing")
            continue

        idle = now - workspace.last_used_at
        if workspace.status in ("ready", "preparing") and docker_status == "running" and idle > workspace.ttl_seconds:
            await asyncio.to_thread(docker.stop, workspace.container_id)
            store.update(workspace.id, status="stopped")
            log.info("stopped idle sandbox %s after %ss", workspace.id, int(idle))
        elif workspace.status == "stopped" and docker_status == "running":
            store.update(workspace.id, status="ready")
