"""Client for the OmniAide sandbox runner.

The runner owns Docker. This module only knows the workspace/exec HTTP API.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import httpx

from core.config.settings import settings


class SandboxError(RuntimeError):
    pass


class SandboxClient:
    def __init__(self, base_url: str, token: str, *, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def _request(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method, url, headers=self._headers(), **kwargs
                )
        except httpx.HTTPError as exc:
            raise SandboxError(f"sandbox runner unavailable: {exc}") from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail") or response.text
            except ValueError:
                detail = response.text
            raise SandboxError(f"sandbox runner {method} {path}: {response.status_code} {detail}")
        if not response.content:
            return None
        return response.json()

    async def list_templates(self) -> list[dict]:
        return await self._request("GET", "/api/templates") or []

    async def get_template(self, template_id: str) -> dict:
        return await self._request("GET", f"/api/templates/{template_id}")

    async def build_template(self, template_id: str) -> dict:
        return await self._request("POST", f"/api/templates/{template_id}/build")

    async def get_build(self, template_id: str) -> dict:
        return await self._request("GET", f"/api/templates/{template_id}/build")

    async def logs(self, workspace_id: str, tail: int = 200) -> dict:
        return await self._request(
            "GET", f"/api/workspaces/{workspace_id}/logs?tail={tail}"
        )

    async def list_workspaces(self, owner_id: str) -> list[dict]:
        data = await self._request(
            "GET", f"/api/workspaces?owner_id={owner_id}"
        )
        return data or []

    async def create_workspace(
        self,
        *,
        owner_id: str,
        project_path: str,
        template: str,
        name: str | None = None,
        ttl_seconds: int | None = None,
    ) -> dict:
        return await self._request(
            "POST",
            "/api/workspaces",
            json={
                "template": template,
                "owner_id": owner_id,
                "project_path": project_path,
                "name": name,
                "ttl_seconds": ttl_seconds,
            },
        )

    async def get_workspace(self, workspace_id: str) -> dict:
        return await self._request("GET", f"/api/workspaces/{workspace_id}")

    async def start_workspace(self, workspace_id: str) -> dict:
        return await self._request("POST", f"/api/workspaces/{workspace_id}/start")

    async def stop_workspace(self, workspace_id: str) -> dict:
        return await self._request("POST", f"/api/workspaces/{workspace_id}/stop")

    async def delete_workspace(self, workspace_id: str) -> dict:
        return await self._request("DELETE", f"/api/workspaces/{workspace_id}")

    async def exec(
        self,
        workspace_id: str,
        command: str | list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: int = 600,
    ) -> dict:
        return await self._request(
            "POST",
            f"/api/workspaces/{workspace_id}/exec",
            json={
                "command": command,
                "cwd": cwd,
                "env": env or {},
                "timeout_seconds": timeout_seconds,
            },
            timeout=timeout_seconds + 30,
        )

    async def stream_exec(
        self,
        workspace_id: str,
        command: str | list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: int = 600,
    ):
        """Yield SSE events from the runner's streaming exec endpoint."""
        url = f"{self.base_url}/api/workspaces/{workspace_id}/exec/stream"
        payload = {
            "command": command,
            "cwd": cwd,
            "env": env or {},
            "timeout_seconds": timeout_seconds,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds + 60) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        detail = (await response.aread()).decode("utf-8", errors="replace")
                        raise SandboxError(
                            f"sandbox runner stream: {response.status_code} {detail}"
                        )
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:].strip()
                        if not raw:
                            continue
                        try:
                            yield json.loads(raw)
                        except json.JSONDecodeError:
                            continue
        except httpx.HTTPError as exc:
            raise SandboxError(f"sandbox runner unavailable: {exc}") from exc

    async def wait_ready(self, workspace_id: str, *, timeout_seconds: int) -> dict:
        deadline = time.monotonic() + max(timeout_seconds, 10)
        last: dict | None = None
        while time.monotonic() < deadline:
            last = await self.get_workspace(workspace_id)
            status = last.get("status")
            if status == "ready":
                return last
            if status == "error":
                raise SandboxError(
                    f"workspace {workspace_id} setup failed: {last.get('error') or 'unknown error'}"
                )
            if status == "stopped":
                await self.start_workspace(workspace_id)
            await asyncio.sleep(2)
        raise SandboxError(
            f"workspace {workspace_id} not ready after {timeout_seconds}s "
            f"(last status: {(last or {}).get('status')})"
        )


_workspace_locks: dict[tuple[str, str], asyncio.Lock] = {}


def _lock_for(key: tuple[str, str]) -> asyncio.Lock:
    lock = _workspace_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _workspace_locks[key] = lock
    return lock


def get_client() -> SandboxClient:
    url = (settings.coding_sandbox_runner_url or "").strip()
    if not url:
        raise SandboxError(
            "CODING_SANDBOX_MODE=docker but CODING_SANDBOX_RUNNER_URL is empty"
        )
    return SandboxClient(url, settings.coding_sandbox_runner_token or "")


async def ensure_workspace(
    owner_id: int,
    project_path: str,
    *,
    template: str | None = None,
    wait_seconds: int | None = None,
) -> dict:
    client = get_client()
    template = template or settings.coding_sandbox_template or "omniaide-base"
    target = str(Path(project_path).expanduser().resolve())
    key = (str(owner_id), target)

    async with _lock_for(key):
        workspaces = await client.list_workspaces(str(owner_id))
        workspace = next(
            (
                item
                for item in workspaces
                if item.get("project_path") == target and item.get("template") == template
            ),
            None,
        )
        if workspace is None:
            workspace = await client.create_workspace(
                owner_id=str(owner_id),
                project_path=target,
                template=template,
                name=Path(target).name,
            )
        status = workspace.get("status")
        if status == "stopped":
            workspace = await client.start_workspace(workspace["id"])
        if workspace.get("status") != "ready":
            workspace = await client.wait_ready(
                workspace["id"],
                timeout_seconds=wait_seconds or settings.coding_sandbox_wait_seconds,
            )
        return workspace


def sandbox_mode() -> str:
    return (settings.coding_sandbox_mode or "local").strip().lower()
