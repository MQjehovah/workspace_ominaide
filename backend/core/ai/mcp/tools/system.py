"""General shell access for the assistant.

Unlike the coding sandbox (which is limited to the user's projects dir), this tool is meant
for everyday server operations: inspecting processes, running ssh/curl, etc.
It runs inside the backend container as the backend user (root in production)
with a scrubbed environment, and every call is classified as ``exec`` so the
Bot asks for approval first.
"""
import asyncio
import os
import signal
from pathlib import Path

from core.ai.mcp.core import MCPCallResponse, MCPContent, MCPTool
from core.config.settings import settings


def _ok(text: str) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=text)])


def _err(text: str) -> MCPCallResponse:
    return MCPCallResponse(isError=True, content=[MCPContent(text=text)])


def _shell_env() -> dict:
    """Minimal env: keep PATH/HOME/proxy, drop database and API secrets."""
    env = {
        "PATH": os.environ.get(
            "PATH", "/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin"
        ),
        "HOME": os.environ.get("HOME") or os.environ.get("USERPROFILE") or "/root",
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        "TERM": os.environ.get("TERM", "dumb"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "PYTHONUNBUFFERED": "1",
    }
    for key in ("SSH_AUTH_SOCK", "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    return env


async def _is_admin(user_id: int) -> bool:
    try:
        from sqlalchemy import select

        from core.auth.domain.models import User
        from core.database.session import async_session

        async with async_session() as db:
            row = (await db.execute(
                select(User.is_admin).where(User.id == user_id)
            )).scalar_one_or_none()
        return bool(row)
    except Exception:
        return False


async def run_shell(user_id: int, args: dict) -> MCPCallResponse:
    if not settings.shell_enabled:
        return _err("shell 工具已被禁用")
    if settings.shell_admin_only and not await _is_admin(user_id):
        return _err("shell 工具仅限管理员使用")
    command = (args.get("command") or "").strip()
    if not command:
        return _err("command 必填")

    cwd_value = (args.get("cwd") or settings.shell_default_cwd or "/app").strip()
    cwd = Path(cwd_value).expanduser()
    if not cwd.exists() or not cwd.is_dir():
        return _err(f"工作目录不存在：{cwd_value}")

    try:
        timeout = int(args.get("timeout_seconds") or settings.shell_timeout_seconds)
    except (TypeError, ValueError):
        timeout = settings.shell_timeout_seconds
    timeout = min(max(timeout, 1), 3600)

    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=str(cwd),
        env=_shell_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        timed_out = True
        try:
            if hasattr(os, "killpg"):
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        stdout_b, stderr_b = await proc.communicate()

    limit = settings.shell_max_output_chars
    stdout = stdout_b.decode("utf-8", errors="replace")[:limit].strip()
    stderr = stderr_b.decode("utf-8", errors="replace")[:min(limit, 8000)].strip()

    lines = [
        f"cwd：{cwd}",
        f"退出码：{proc.returncode}" + ("（超时）" if timed_out else ""),
    ]
    if stdout:
        lines.append(f"\nstdout:\n{stdout}")
    if stderr:
        lines.append(f"\nstderr:\n{stderr}")
    return _ok("\n".join(lines))


TOOLS = [
    (
        MCPTool(
            name="run_shell",
            description=(
                "在服务器后端容器内执行 shell 命令（后端用户权限，可运行 ssh、curl、"
                "进程/文件检查等）。命令需要用户审批。不要用它修改代码，改代码请用 "
                "delegate_coding；Coding Agent 只限制在当前用户的项目目录内。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 shell 命令"},
                    "cwd": {
                        "type": "string",
                        "description": "执行目录，默认 /app",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "超时秒数，默认 600，最大 3600",
                    },
                },
                "required": ["command"],
            },
        ),
        run_shell,
    ),
]
