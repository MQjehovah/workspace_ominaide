"""Request and response models for the sandbox runner API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Resources(BaseModel):
    cpus: float = Field(default=2.0, gt=0)
    memory: str = "4g"
    pids: int = Field(default=512, gt=0)


class TemplateBuild(BaseModel):
    context: str
    dockerfile: str = "Dockerfile"
    args: dict[str, str] = Field(default_factory=dict)
    tag: str | None = None


class Template(BaseModel):
    id: str
    name: str
    description: str = ""
    image: str
    build: TemplateBuild | None = None
    workdir: str = "/workspace"
    user: str = "1001:1000"
    shell: str = "/bin/bash"
    env: dict[str, str] = Field(default_factory=dict)
    ports: list[int] = Field(default_factory=list)
    setup: list[str] = Field(default_factory=list)
    resources: Resources = Field(default_factory=Resources)
    ttl_seconds: int | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class TemplateSummary(BaseModel):
    id: str
    name: str
    description: str = ""
    image: str
    workdir: str
    ports: list[int]
    setup_count: int
    has_build: bool = False


class WorkspaceCreate(BaseModel):
    template: str = "omniaide-base"
    owner_id: str
    name: str | None = None
    project_path: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    ttl_seconds: int | None = None


class Workspace(BaseModel):
    id: str
    owner_id: str
    template: str
    name: str
    project_path: str
    container_id: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    status: str
    created_at: float
    last_used_at: float
    ttl_seconds: int
    error: str | None = None
    setup_log: str | None = None


class ExecRequest(BaseModel):
    command: str | list[str]
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int | None = None


class ExecResult(BaseModel):
    workspace_id: str
    exit_code: int
    timed_out: bool
    stdout: str
    stderr: str


class PortBinding(BaseModel):
    container_port: str
    host_ip: str | None = None
    host_port: str | None = None


class WorkspaceDetail(Workspace):
    docker_status: str | None = None
    ports: list[PortBinding] = Field(default_factory=list)
    setup_running: bool = False


class BuildStatus(BaseModel):
    template_id: str
    status: str = "idle"
    log: str | None = None
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None


class Health(BaseModel):
    status: str
    docker: bool
    templates: int
    workspaces: int
    error: str | None = None


class ErrorResponse(BaseModel):
    detail: str
    extra: dict[str, Any] | None = None
