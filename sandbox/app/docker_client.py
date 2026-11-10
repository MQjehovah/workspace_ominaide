"""Thin async-friendly wrapper around the Docker SDK.

The runner talks to Docker through the mounted socket. Only this module is
allowed to construct bind mounts or touch containers.
"""

from __future__ import annotations

import posixpath
import shlex
from pathlib import Path
from typing import Iterator

import docker
from docker.errors import APIError, DockerException, NotFound

from app.models import PortBinding, Template, Workspace
from app.config import Settings


class SandboxDockerError(RuntimeError):
    pass


class SandboxDocker:
    def __init__(self, config: Settings):
        self.config = config
        try:
            if config.docker_host:
                self.client = docker.DockerClient(base_url=config.docker_host)
            else:
                self.client = docker.from_env()
        except DockerException as exc:  # pragma: no cover - depends on host
            raise SandboxDockerError(f"cannot connect to Docker: {exc}") from exc

    # ---------------------------------------------------------------- helpers

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except DockerException:
            return False

    def ensure_network(self) -> None:
        name = self.config.network.strip()
        if not name:
            return
        try:
            self.client.networks.get(name)
        except NotFound:
            self.client.networks.create(name, driver="bridge", check_duplicate=True)

    def validate_project_path(self, project_path: str | None, *, create: bool = False) -> Path:
        root = self.config.data_root_path
        if project_path:
            path = Path(project_path).expanduser().resolve()
        else:
            path = root
        if not self._under_allowed_roots(path):
            raise SandboxDockerError(
                f"project_path is outside allowed roots: {path}"
            )
        if create:
            path.mkdir(parents=True, exist_ok=True)
        if not path.exists() or not path.is_dir():
            raise SandboxDockerError(f"project_path is not a directory: {path}")
        return path

    def _under_allowed_roots(self, path: Path) -> bool:
        roots = self.config.allowed_root_paths
        return any(path == root or root in path.parents for root in roots)

    def container_name(self, workspace_id: str) -> str:
        return f"{self.config.name_prefix}-{workspace_id}"

    def _labels(self, workspace: Workspace) -> dict[str, str]:
        return {
            "omniaide.sandbox": "1",
            "omniaide.workspace_id": workspace.id,
            "omniaide.owner_id": workspace.owner_id,
            "omniaide.template": workspace.template,
            "omniaide.project_path": workspace.project_path,
        }

    def _bind_source(self, path: Path) -> str:
        """Translate a path inside the runner to the host path Docker needs."""
        host_root = self.config.host_data_root.strip()
        if not host_root:
            return str(path)
        container_root = Path("/data")
        try:
            relative = path.relative_to(container_root)
        except ValueError:
            return str(path)
        return str(Path(host_root) / relative)

    def _home_volume(self, workspace: Workspace) -> str:
        name = f"{self.config.name_prefix}-{workspace.id}-home"
        try:
            self.client.volumes.get(name)
        except NotFound:
            self.client.volumes.create(name=name, labels=self._labels(workspace))
        return name

    # ------------------------------------------------------------- lifecycle

    def create(self, workspace: Workspace, template: Template) -> str:
        self.ensure_network()
        project = self.validate_project_path(workspace.project_path, create=True)
        home_volume = self._home_volume(workspace)

        volumes = {
            self._bind_source(project): {"bind": template.workdir, "mode": "rw"},
            home_volume: {"bind": "/home/agent", "mode": "rw"},
        }
        ports = {f"{port}/tcp": None for port in template.ports}
        environment = {
            "HOME": "/home/agent",
            "TERM": "xterm-256color",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            **template.env,
            **workspace.env,
        }

        run_kwargs = {
            "image": template.image,
            "command": ["sleep", "infinity"],
            "name": self.container_name(workspace.id),
            "detach": True,
            "working_dir": template.workdir,
            "user": template.user,
            "environment": environment,
            "volumes": volumes,
            "labels": {**self._labels(workspace), **template.labels},
            "ports": ports,
            "nano_cpus": int(template.resources.cpus * 1_000_000_000),
            "mem_limit": template.resources.memory,
            "pids_limit": template.resources.pids,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges"],
            "init": True,
            "auto_remove": False,
            "restart_policy": {"Name": "no"},
        }
        if self.config.network.strip():
            run_kwargs["network"] = self.config.network.strip()
        try:
            container = self.client.containers.run(**run_kwargs)
        except (APIError, DockerException) as exc:
            raise SandboxDockerError(f"cannot create container: {exc}") from exc
        return container.id

    def start(self, container_id: str) -> None:
        try:
            self.client.containers.get(container_id).start()
        except (NotFound, APIError, DockerException) as exc:
            raise SandboxDockerError(f"cannot start container: {exc}") from exc

    def stop(self, container_id: str, timeout: int = 10) -> None:
        try:
            self.client.containers.get(container_id).stop(timeout=timeout)
        except NotFound:
            return
        except (APIError, DockerException) as exc:
            raise SandboxDockerError(f"cannot stop container: {exc}") from exc

    def remove(self, container_id: str, *, remove_home: bool = True, workspace_id: str = "") -> None:
        try:
            container = self.client.containers.get(container_id)
            container.remove(force=True, v=False)
        except NotFound:
            pass
        except (APIError, DockerException) as exc:
            raise SandboxDockerError(f"cannot remove container: {exc}") from exc
        if remove_home and workspace_id:
            name = f"{self.config.name_prefix}-{workspace_id}-home"
            try:
                self.client.volumes.get(name).remove(force=True)
            except NotFound:
                pass
            except (APIError, DockerException):
                pass

    def status(self, container_id: str | None) -> str | None:
        if not container_id:
            return None
        try:
            return self.client.containers.get(container_id).status
        except NotFound:
            return "missing"
        except (APIError, DockerException):
            return None

    def ports(self, container_id: str | None) -> list[PortBinding]:
        if not container_id:
            return []
        try:
            attrs = self.client.containers.get(container_id).attrs
        except (NotFound, APIError, DockerException):
            return []
        bindings: list[PortBinding] = []
        for container_port, hosts in (attrs.get("NetworkSettings", {}).get("Ports") or {}).items():
            if not hosts:
                bindings.append(PortBinding(container_port=container_port))
                continue
            for host in hosts:
                bindings.append(
                    PortBinding(
                        container_port=container_port,
                        host_ip=host.get("HostIp"),
                        host_port=host.get("HostPort"),
                    )
                )
        return bindings

    # ------------------------------------------------------------------ exec

    def _validate_cwd(self, workdir: str, cwd: str | None) -> str:
        if not cwd:
            return workdir
        if cwd.startswith("/"):
            candidate = posixpath.normpath(cwd)
        else:
            candidate = posixpath.normpath(posixpath.join(workdir, cwd))
        if candidate != workdir and not candidate.startswith(workdir.rstrip("/") + "/"):
            raise SandboxDockerError(f"cwd escapes workspace: {cwd}")
        return candidate

    def _build_command(self, command: str | list[str], timeout: int) -> list[str]:
        if isinstance(command, str):
            base = ["/bin/sh", "-lc", command]
        else:
            base = [str(item) for item in command]
            if not base:
                raise SandboxDockerError("command is empty")
        if timeout > 0:
            return ["timeout", "--signal=KILL", str(timeout), *base]
        return base

    def exec(
        self,
        container_id: str,
        command: str | list[str],
        *,
        workdir: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 600,
    ) -> tuple[int, str, str, bool]:
        try:
            container = self.client.containers.get(container_id)
        except NotFound as exc:
            raise SandboxDockerError("workspace container not found") from exc
        if container.status != "running":
            raise SandboxDockerError(f"workspace container is {container.status}")
        resolved_cwd = self._validate_cwd(workdir, cwd)
        argv = self._build_command(command, timeout)
        try:
            created = self.client.api.exec_create(
                container.id,
                argv,
                workdir=resolved_cwd,
                environment={k: str(v) for k, v in (env or {}).items()},
                stdout=True,
                stderr=True,
            )
            exec_id = created["Id"]
            stdout_b, stderr_b = self.client.api.exec_start(exec_id, demux=True) or (b"", b"")
            code = int(self.client.api.exec_inspect(exec_id).get("ExitCode") or 0)
        except (NotFound, APIError, DockerException) as exc:
            raise SandboxDockerError(f"exec failed: {exc}") from exc
        return (
            code,
            (stdout_b or b"").decode("utf-8", errors="replace"),
            (stderr_b or b"").decode("utf-8", errors="replace"),
            code in (124, 137),
        )

    def stream(
        self,
        container_id: str,
        command: str | list[str],
        *,
        workdir: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 600,
    ) -> Iterator[tuple[str, bytes]]:
        try:
            container = self.client.containers.get(container_id)
        except NotFound as exc:
            raise SandboxDockerError("workspace container not found") from exc
        if container.status != "running":
            raise SandboxDockerError(f"workspace container is {container.status}")
        resolved_cwd = self._validate_cwd(workdir, cwd)
        argv = self._build_command(command, timeout)
        try:
            created = self.client.api.exec_create(
                container.id,
                argv,
                workdir=resolved_cwd,
                environment={k: str(v) for k, v in (env or {}).items()},
                stdout=True,
                stderr=True,
            )
            exec_id = created["Id"]
            stream = self.client.api.exec_start(exec_id, stream=True, demux=True)
            for stdout_b, stderr_b in stream:
                if stdout_b:
                    yield "stdout", stdout_b
                if stderr_b:
                    yield "stderr", stderr_b
        except (NotFound, APIError, DockerException) as exc:
            raise SandboxDockerError(f"stream failed: {exc}") from exc

    def logs(self, container_id: str, tail: int = 200) -> str:
        try:
            container = self.client.containers.get(container_id)
            return container.logs(tail=tail).decode("utf-8", errors="replace")
        except (NotFound, APIError, DockerException) as exc:
            raise SandboxDockerError(f"cannot read logs: {exc}") from exc

    def shell_quote(self, command: str) -> str:
        return shlex.quote(command)
