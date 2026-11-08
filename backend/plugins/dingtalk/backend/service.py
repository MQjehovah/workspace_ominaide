"""Per-user DingTalk account binding.

Each user owns their DWS config directory and token store under
``<workspace_root>/<user_id>/dingtalk``. Login runs the CLI in that environment
so tokens never leak between accounts.
"""

from __future__ import annotations

from core.logging import get_logger
log = get_logger(__name__)

import asyncio
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field

from sqlalchemy import select

from core.crypto import encrypt_secret
from core.database.session import async_session
from core.mcp_hub.models import McpServer
from core.paths import user_root
from plugins.dingtalk.backend.paths import dingtalk_env, dingtalk_root, ensure_dingtalk_workspace

DEVICE_CODE_RE = re.compile(r"授权码[:：]\s*([A-Za-z0-9-]+)")
DEVICE_URL_RE = re.compile(r"https://\S*verify\.htm\S*")
SESSION_TTL = 20 * 60


def _dws_binary() -> str:
    return os.environ.get("DWS_BIN") or shutil.which("dws") or "dws"


def _clean_url(value: str) -> str:
    return value.rstrip(".,;，。；)")


async def _find_dingtalk_server(user_id: int) -> McpServer | None:
    async with async_session() as db:
        rows = (await db.execute(
            select(McpServer)
            .where(
                McpServer.user_id == user_id,
                McpServer.enabled == True,  # noqa: E712
            )
            .order_by(McpServer.id)
        )).scalars().all()
    return next((row for row in rows if _is_dingtalk(row)), None)


def _is_dingtalk(row: McpServer) -> bool:
    if (row.slug or "").lower().startswith("dingtalk"):
        return True
    if "钉钉" in (row.name or ""):
        return True
    return any(
        "plugins.dingtalk.mcp_server" in str(arg)
        or "mcp_servers.dingtalk" in str(arg)
        for arg in (row.args or [])
    )


async def ensure_dingtalk_server(user_id: int) -> McpServer:
    """Return this user's DingTalk MCP server, creating or upgrading it."""
    ensure_dingtalk_workspace(user_id)
    env = dingtalk_env(user_id)
    async with async_session() as db:
        rows = list((await db.execute(
            select(McpServer)
            .where(McpServer.user_id == user_id)
            .order_by(McpServer.id)
        )).scalars().all())
        row = next((item for item in rows if _is_dingtalk(item)), None)
        if row is None:
            row = McpServer(
                user_id=user_id,
                slug=f"dingtalk-{user_id}",
                name="钉钉",
                scope="internal",
                owner_plugin="dingtalk",
                expose_tools=False,
                transport="stdio",
                command="python",
                args=["-m", "plugins.dingtalk.mcp_server"],
                risk_default="read",
                enabled=True,
                auto_start=True,
            )
            db.add(row)
        else:
            target_slug = f"dingtalk-{user_id}"
            clash = next(
                (item for item in rows
                 if item.id != row.id and item.slug == target_slug),
                None,
            )
            if clash is None:
                row.slug = target_slug
            row.name = row.name or "钉钉"
            row.transport = "stdio"
            # Legacy rows may point at ``mcp_servers.dingtalk`` or a custom
            # command; always replace them with the plugin-owned server.
            row.command = "python"
            row.args = ["-m", "plugins.dingtalk.mcp_server"]
            row.scope = "internal"
            row.owner_plugin = "dingtalk"
            row.expose_tools = False
            row.enabled = True
            row.auto_start = True
        row.env_encrypted = encrypt_secret(json.dumps(env, ensure_ascii=False))
        await db.commit()
        await db.refresh(row)
        return row


async def migrate_existing_servers() -> None:
    """Move legacy DingTalk MCP rows to the plugin-private namespace."""
    async with async_session() as db:
        rows = list((await db.execute(select(McpServer))).scalars().all())
        users = sorted({int(row.user_id) for row in rows if _is_dingtalk(row)})
    for user_id in users:
        try:
            await ensure_dingtalk_server(user_id)
        except Exception as e:
            log.warning(f"[dingtalk] migrate user {user_id} failed: {e}")


async def connect_dingtalk_server(user_id: int) -> None:
    try:
        from core.mcp_hub.hub import mcp_hub

        row = await ensure_dingtalk_server(user_id)
        await mcp_hub.connect_server(row.id, user_id)
    except Exception as e:
        log.warning(f"[dingtalk] connect server for user {user_id} failed: {e}")


def _authenticated(payload: dict) -> bool:
    for key in ("authenticated", "loggedIn", "logged_in", "isAuthenticated"):
        if key in payload:
            return bool(payload[key])
    profile = payload.get("profile") or payload.get("currentProfile") or {}
    if isinstance(profile, dict) and profile:
        return True
    data = payload.get("data")
    if isinstance(data, dict):
        return _authenticated(data)
    return False


async def dingtalk_status(user_id: int) -> dict:
    from plugins.dingtalk.mcp_server.dws_client import DwSError, run_dws

    ensure_dingtalk_workspace(user_id)
    payload: dict = {}
    error: str | None = None
    try:
        payload = await run_dws(
            ["auth", "status", "--format", "json"],
            timeout=40,
            env=dingtalk_env(user_id),
        )
        payload = payload or {}
    except DwSError as e:
        error = str(e)[:500]
    except Exception as e:
        error = str(e)[:500]

    server = await _find_dingtalk_server(user_id)
    return {
        "configured": bool(server and _is_dingtalk(server)),
        "authenticated": _authenticated(payload) if not error else False,
        "status": payload,
        "error": error,
        "workspace": str(user_root(user_id)),
        "dingtalk_dir": str(dingtalk_root(user_id)),
    }


@dataclass
class LoginSession:
    user_id: int
    proc: asyncio.subprocess.Process
    started_at: float = field(default_factory=time.time)
    status: str = "pending"
    user_code: str | None = None
    verification_url: str | None = None
    error: str | None = None
    output: list[str] = field(default_factory=list)
    reader: asyncio.Task | None = None


_sessions: dict[int, LoginSession] = {}
_lock = asyncio.Lock()


def get_login_session(user_id: int) -> LoginSession | None:
    return _sessions.get(user_id)


def cancel_login(user_id: int) -> None:
    """Terminate a pending device-flow login owned by this user."""
    session = _sessions.pop(user_id, None)
    if session is not None and session.proc.returncode is None:
        try:
            session.proc.terminate()
        except Exception as exc:
            log.debug("terminate login process for user %s failed: %s", user_id, exc)


async def _read_login_output(session: LoginSession) -> None:
    proc = session.proc
    assert proc.stdout is not None
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").rstrip()
        if not text:
            continue
        session.output.append(text)
        code = DEVICE_CODE_RE.search(text)
        if code:
            session.user_code = code.group(1)
        url = DEVICE_URL_RE.search(text)
        if url:
            session.verification_url = _clean_url(url.group(0))
    returncode = await proc.wait()
    if returncode == 0:
        session.status = "authorized"
        await connect_dingtalk_server(session.user_id)
    else:
        session.status = "failed"
        tail = "\n".join(line for line in session.output[-6:] if line.strip())
        session.error = (tail or f"dws auth login exited {returncode}")[:1000]


async def start_login(user_id: int) -> LoginSession:
    """Start (or return) the device-flow login for this user."""
    async with _lock:
        existing = _sessions.get(user_id)
        if existing is not None:
            # Reuse a live device-flow request, but always allow an explicit
            # rebind after the previous flow completed.
            if existing.status == "pending" and existing.proc.returncode is None:
                return existing
            if time.time() - existing.started_at < SESSION_TTL and existing.status == "pending":
                return existing

        ensure_dingtalk_workspace(user_id)
        await ensure_dingtalk_server(user_id)
        env = {**os.environ, **dingtalk_env(user_id)}
        proc = await asyncio.create_subprocess_exec(
            _dws_binary(),
            "auth", "login", "--device", "--recommend",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        session = LoginSession(user_id=user_id, proc=proc)
        _sessions[user_id] = session
        session.reader = asyncio.create_task(_read_login_output(session))
        return session


def session_out(session: LoginSession) -> dict:
    return {
        "status": session.status,
        "user_code": session.user_code,
        "verification_url": session.verification_url,
        "error": session.error,
        "expires_in": max(0, int(SESSION_TTL - (time.time() - session.started_at))),
    }


async def logout(user_id: int) -> dict:
    from plugins.dingtalk.mcp_server.dws_client import DwSError, run_dws

    cancel_login(user_id)
    try:
        await run_dws(
            ["auth", "logout", "--yes"],
            timeout=60,
            env=dingtalk_env(user_id),
        )
        return {"status": "logged_out"}
    except DwSError as e:
        return {"status": "error", "error": str(e)[:500]}
