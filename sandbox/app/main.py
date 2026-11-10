"""Sandbox runner service entrypoint."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.config import settings
from app.docker_client import SandboxDocker, SandboxDockerError
from app.reaper import reaper_loop
from app.router import router
from app.store import WorkspaceStore
from app.templates import TemplateError, TemplateRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("sandbox-runner")


@asynccontextmanager
async def lifespan(app: FastAPI):
    templates_dir = Path(settings.templates_dir)
    if not templates_dir.is_absolute():
        templates_dir = Path(__file__).resolve().parent.parent / settings.templates_dir
    registry = TemplateRegistry(templates_dir)
    try:
        loaded = registry.load()
        log.info("loaded %s sandbox templates from %s", len(loaded), templates_dir)
    except TemplateError as exc:
        log.error("template load failed: %s", exc)
        raise

    store = WorkspaceStore(settings.state_db)

    docker: SandboxDocker | None = None
    try:
        docker = SandboxDocker(settings)
        if docker.ping():
            log.info("docker is reachable")
        else:
            log.warning("docker ping failed; endpoints will return 503")
            docker = None
    except SandboxDockerError as exc:
        log.warning("docker is unavailable: %s", exc)
        docker = None

    app.state.settings = settings
    app.state.store = store
    app.state.registry = registry
    app.state.docker = docker

    reaper = asyncio.create_task(
        reaper_loop(
            store,
            docker,
            interval=settings.reaper_interval_seconds,
            log=log,
        )
    )
    try:
        yield
    finally:
        reaper.cancel()
        try:
            await reaper
        except asyncio.CancelledError:
            pass
        store.close()


app = FastAPI(
    title="OmniAide Sandbox Runner",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/")
async def root():
    return {
        "name": "sandbox-runner",
        "docs": "/docs",
        "health": "/api/health",
    }
