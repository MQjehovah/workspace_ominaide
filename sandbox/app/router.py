"""HTTP API for the sandbox runner."""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.docker_client import SandboxDocker, SandboxDockerError
from app.models import (
    ExecRequest,
    ExecResult,
    Health,
    TemplateSummary,
    Workspace,
    WorkspaceCreate,
    WorkspaceDetail,
)
from app.store import WorkspaceStore
from app.templates import TemplateError, TemplateRegistry

router = APIRouter(prefix="/api")

MAX_OUTPUT_CHARS = 200_000


def _state(request: Request):
    return request.app.state


async def require_token(request: Request, authorization: str | None = Header(default=None)) -> None:
    expected = _state(request).settings.runner_token
    if not expected:
        return
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid sandbox runner token")


def _docker(request: Request) -> SandboxDocker:
    docker = _state(request).docker
    if docker is None:
        raise HTTPException(status_code=503, detail="docker is unavailable")
    return docker


def _store(request: Request) -> WorkspaceStore:
    return _state(request).store


def _registry(request: Request) -> TemplateRegistry:
    return _state(request).registry


def _get_workspace(request: Request, workspace_id: str) -> Workspace:
    workspace = _store(request).get(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return workspace


@router.get("/health", response_model=Health)
async def health(request: Request) -> Health:
    docker = _state(request).docker
    ok = bool(docker and docker.ping())
    return Health(
        status="ok" if ok else "degraded",
        docker=ok,
        templates=len(_registry(request).list()),
        workspaces=_store(request).count(),
        error=None if ok else "docker is unavailable",
    )


@router.get("/templates", response_model=list[TemplateSummary])
async def list_templates(request: Request, _: None = Depends(require_token)) -> list[TemplateSummary]:
    return _registry(request).list()


@router.get("/templates/{template_id}")
async def get_template(request: Request, template_id: str, _: None = Depends(require_token)):
    try:
        return _registry(request).get(template_id)
    except TemplateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/workspaces", response_model=Workspace, status_code=201)
async def create_workspace(
    request: Request,
    body: WorkspaceCreate,
    background: BackgroundTasks,
    _: None = Depends(require_token),
) -> Workspace:
    if not body.owner_id.strip():
        raise HTTPException(status_code=400, detail="owner_id is required")
    try:
        template = _registry(request).get(body.template)
    except TemplateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    store = _store(request)
    existing = store.list(body.owner_id)
    max_workspaces = _state(request).settings.max_workspaces_per_owner
    if len(existing) >= max_workspaces:
        raise HTTPException(
            status_code=429,
            detail=f"owner already has {len(existing)} workspaces (max {max_workspaces})",
        )

    docker = _docker(request)
    workspace_id = "ws-" + uuid.uuid4().hex[:12]
    try:
        project = docker.validate_project_path(body.project_path, create=True)
    except SandboxDockerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ttl = body.ttl_seconds or template.ttl_seconds or _state(request).settings.default_ttl_seconds
    now = time.time()
    workspace = Workspace(
        id=workspace_id,
        owner_id=body.owner_id,
        template=template.id,
        name=body.name or f"{template.name} {workspace_id[-4:]}",
        project_path=str(project),
        env=body.env,
        status="creating",
        created_at=now,
        last_used_at=now,
        ttl_seconds=ttl,
    )
    store.create(workspace)
    background.add_task(_prepare_workspace, request.app, workspace_id)
    return workspace


async def _prepare_workspace(app, workspace_id: str) -> None:
    store: WorkspaceStore = app.state.store
    docker: SandboxDocker | None = app.state.docker
    workspace = store.get(workspace_id)
    if workspace is None or docker is None:
        return
    try:
        template = app.state.registry.get(workspace.template)
        container_id = await asyncio.to_thread(docker.create, workspace, template)
        store.update(workspace_id, container_id=container_id, status="preparing")
        if template.setup:
            lines: list[str] = []
            for index, command in enumerate(template.setup, 1):
                code, stdout, stderr, timed_out = await asyncio.to_thread(
                    docker.exec,
                    container_id,
                    command,
                    workdir=template.workdir,
                    timeout=app.state.settings.setup_timeout_seconds,
                )
                lines.append(f"$ {command}\n[exit {code}]")
                if stdout:
                    lines.append(stdout[-8000:])
                if stderr:
                    lines.append(stderr[-8000:])
                if timed_out:
                    raise SandboxDockerError(f"setup command timed out: {command}")
                if code != 0:
                    raise SandboxDockerError(f"setup command failed ({code}): {command}")
            store.update(workspace_id, status="ready", setup_log="\n".join(lines))
        else:
            store.update(workspace_id, status="ready")
    except Exception as exc:  # keep the container for logs, but surface the error
        store.update(workspace_id, status="error", error=str(exc)[:4000])


@router.get("/workspaces", response_model=list[Workspace])
async def list_workspaces(
    request: Request,
    owner_id: str | None = None,
    _: None = Depends(require_token),
) -> list[Workspace]:
    return _store(request).list(owner_id)


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceDetail)
async def get_workspace(
    request: Request,
    workspace_id: str,
    _: None = Depends(require_token),
) -> WorkspaceDetail:
    workspace = _get_workspace(request, workspace_id)
    docker = _docker(request)
    detail = WorkspaceDetail(**workspace.model_dump())
    detail.docker_status = await asyncio.to_thread(docker.status, workspace.container_id)
    detail.ports = await asyncio.to_thread(docker.ports, workspace.container_id)
    detail.setup_running = workspace.status in ("creating", "preparing")
    return detail


@router.post("/workspaces/{workspace_id}/start", response_model=Workspace)
async def start_workspace(
    request: Request,
    workspace_id: str,
    _: None = Depends(require_token),
) -> Workspace:
    workspace = _get_workspace(request, workspace_id)
    if not workspace.container_id:
        raise HTTPException(status_code=409, detail="workspace has no container yet")
    docker = _docker(request)
    try:
        await asyncio.to_thread(docker.start, workspace.container_id)
    except SandboxDockerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    updated = _store(request).update(workspace_id, status="ready", error=None)
    return updated or workspace


@router.post("/workspaces/{workspace_id}/stop", response_model=Workspace)
async def stop_workspace(
    request: Request,
    workspace_id: str,
    _: None = Depends(require_token),
) -> Workspace:
    workspace = _get_workspace(request, workspace_id)
    if not workspace.container_id:
        raise HTTPException(status_code=409, detail="workspace has no container yet")
    docker = _docker(request)
    try:
        await asyncio.to_thread(docker.stop, workspace.container_id)
    except SandboxDockerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    updated = _store(request).update(workspace_id, status="stopped")
    return updated or workspace


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(
    request: Request,
    workspace_id: str,
    remove_home: bool = True,
    _: None = Depends(require_token),
) -> dict:
    workspace = _get_workspace(request, workspace_id)
    docker = _docker(request)
    if workspace.container_id:
        try:
            await asyncio.to_thread(
                docker.remove,
                workspace.container_id,
                remove_home=remove_home,
                workspace_id=workspace.id,
            )
        except SandboxDockerError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    _store(request).delete(workspace_id)
    return {"deleted": True, "workspace_id": workspace_id}


@router.post("/workspaces/{workspace_id}/setup", response_model=Workspace)
async def rerun_setup(
    request: Request,
    workspace_id: str,
    background: BackgroundTasks,
    _: None = Depends(require_token),
) -> Workspace:
    workspace = _get_workspace(request, workspace_id)
    if not workspace.container_id:
        raise HTTPException(status_code=409, detail="workspace has no container yet")
    _store(request).update(workspace_id, status="preparing", error=None)
    background.add_task(_prepare_setup_only, request.app, workspace_id)
    return _store(request).get(workspace_id) or workspace


async def _prepare_setup_only(app, workspace_id: str) -> None:
    store: WorkspaceStore = app.state.store
    docker: SandboxDocker | None = app.state.docker
    workspace = store.get(workspace_id)
    if workspace is None or docker is None or not workspace.container_id:
        return
    try:
        template = app.state.registry.get(workspace.template)
        lines: list[str] = []
        for command in template.setup:
            code, stdout, stderr, timed_out = await asyncio.to_thread(
                docker.exec,
                workspace.container_id,
                command,
                workdir=template.workdir,
                timeout=app.state.settings.setup_timeout_seconds,
            )
            lines.append(f"$ {command}\n[exit {code}]")
            if stdout:
                lines.append(stdout[-8000:])
            if stderr:
                lines.append(stderr[-8000:])
            if timed_out or code != 0:
                raise SandboxDockerError(f"setup command failed ({code}): {command}")
        store.update(workspace_id, status="ready", setup_log="\n".join(lines))
    except Exception as exc:
        store.update(workspace_id, status="error", error=str(exc)[:4000])


@router.get("/workspaces/{workspace_id}/logs")
async def workspace_logs(
    request: Request,
    workspace_id: str,
    tail: int = 200,
    _: None = Depends(require_token),
) -> dict:
    workspace = _get_workspace(request, workspace_id)
    if not workspace.container_id:
        return {"logs": ""}
    docker = _docker(request)
    try:
        text = await asyncio.to_thread(docker.logs, workspace.container_id, tail)
    except SandboxDockerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"logs": text}


@router.post("/workspaces/{workspace_id}/exec", response_model=ExecResult)
async def exec_command(
    request: Request,
    workspace_id: str,
    body: ExecRequest,
    _: None = Depends(require_token),
) -> ExecResult:
    workspace = _get_workspace(request, workspace_id)
    if not workspace.container_id:
        raise HTTPException(status_code=409, detail="workspace has no container yet")
    if workspace.status not in ("ready", "preparing"):
        raise HTTPException(
            status_code=409,
            detail=f"workspace is {workspace.status}; start it before exec",
        )
    docker = _docker(request)
    try:
        template = _registry(request).get(workspace.template)
        code, stdout, stderr, timed_out = await asyncio.to_thread(
            docker.exec,
            workspace.container_id,
            body.command,
            workdir=template.workdir,
            cwd=body.cwd,
            env=body.env,
            timeout=body.timeout_seconds or _state(request).settings.exec_timeout_seconds,
        )
    except (SandboxDockerError, TemplateError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _store(request).touch(workspace_id)
    return ExecResult(
        workspace_id=workspace_id,
        exit_code=code,
        timed_out=timed_out,
        stdout=stdout[-MAX_OUTPUT_CHARS:],
        stderr=stderr[-MAX_OUTPUT_CHARS:],
    )


@router.post("/workspaces/{workspace_id}/exec/stream")
async def exec_stream(
    request: Request,
    workspace_id: str,
    body: ExecRequest,
    _: None = Depends(require_token),
) -> StreamingResponse:
    workspace = _get_workspace(request, workspace_id)
    if not workspace.container_id:
        raise HTTPException(status_code=409, detail="workspace has no container yet")
    if workspace.status != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"workspace is {workspace.status}; start it before exec",
        )
    docker = _docker(request)
    template = _registry(request).get(workspace.template)
    timeout = body.timeout_seconds or _state(request).settings.exec_timeout_seconds
    _store(request).touch(workspace_id)

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def worker() -> None:
        try:
            for stream_name, chunk in docker.stream(
                workspace.container_id,
                body.command,
                workdir=template.workdir,
                cwd=body.cwd,
                env=body.env,
                timeout=timeout,
            ):
                text = chunk.decode("utf-8", errors="replace")
                loop.call_soon_threadsafe(
                    queue.put_nowait, {"type": "chunk", "stream": stream_name, "text": text}
                )
        except Exception as exc:
            loop.call_soon_threadsafe(
                queue.put_nowait, {"type": "error", "error": str(exc)}
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "done"})

    threading.Thread(target=worker, daemon=True).start()

    async def events():
        while True:
            item = await queue.get()
            yield "data: " + json.dumps(item, ensure_ascii=False) + "\n\n"
            if item.get("type") == "done":
                break

    return StreamingResponse(events(), media_type="text/event-stream")
