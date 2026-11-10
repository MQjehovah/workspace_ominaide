"""Route built-in coding ``run_command`` calls into a sandbox container."""

from __future__ import annotations

from pathlib import Path

from ai.coding import workspace as workspace_tools
from ai.coding.sandbox_client import (
    SandboxError,
    ensure_workspace,
    get_client,
)
from core.config.settings import settings


def _sandbox_env(identity: dict | None) -> dict[str, str]:
    env = {
        "GIT_TERMINAL_PROMPT": "0",
        "PAGER": "cat",
        "GIT_PAGER": "cat",
        "PYTHONUNBUFFERED": "1",
        "GIT_CONFIG_KEY_0": "safe.directory",
        "GIT_CONFIG_VALUE_0": "*",
        "GIT_CONFIG_COUNT": "1",
    }
    if identity:
        if identity.get("name"):
            env["GIT_AUTHOR_NAME"] = str(identity["name"])
            env["GIT_COMMITTER_NAME"] = str(identity["name"])
        if identity.get("email"):
            env["GIT_AUTHOR_EMAIL"] = str(identity["email"])
            env["GIT_COMMITTER_EMAIL"] = str(identity["email"])
    return env


def _relative_cwd(project: str, raw: str | None) -> str:
    root = Path(project).expanduser().resolve()
    if not raw:
        return "."
    target = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"cwd escapes project root: {raw}")
    return target.relative_to(root).as_posix() or "."


async def run_command_in_sandbox(
    user_id: int,
    project: str,
    args: dict,
    *,
    allow_push: bool = False,
    allow_commit: bool = False,
    identity: dict | None = None,
    ssh_key: str | None = None,
) -> dict:
    command = str(args.get("command") or "")
    if not command.strip():
        return {"error": "command is required"}

    violation = workspace_tools.git_policy_violation(
        command, allow_commit=allow_commit, allow_push=allow_push
    )
    if violation:
        return {"error": violation}
    if workspace_tools.contains_sensitive_reference(command):
        return {"error": "sensitive file (.env / key) is blocked"}

    try:
        cwd = _relative_cwd(project, str(args.get("cwd") or "").strip() or None)
    except ValueError as exc:
        return {"error": str(exc)}

    try:
        timeout = int(args.get("timeout_ms") or settings.coding_command_timeout_ms)
    except (TypeError, ValueError):
        timeout = settings.coding_command_timeout_ms
    timeout = min(max(timeout, 1000), 600_000)

    try:
        sandbox = await ensure_workspace(user_id, project)
        client = get_client()
        result = await client.exec(
            sandbox["id"],
            command,
            cwd=cwd,
            env=_sandbox_env(identity),
            timeout_seconds=max(1, timeout // 1000),
        )
    except SandboxError as exc:
        return {"error": str(exc)}

    return {
        "code": result.get("exit_code"),
        "timed_out": bool(result.get("timed_out")),
        "stdout": workspace_tools.clamp(
            str(result.get("stdout") or ""), workspace_tools.MAX_COMMAND_OUTPUT
        ),
        "stderr": workspace_tools.clamp(
            str(result.get("stderr") or ""), workspace_tools.MAX_COMMAND_OUTPUT
        ),
        "sandbox": sandbox.get("id"),
    }
