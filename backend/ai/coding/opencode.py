"""OpenCode external coding engine.

OpenCode owns its own agent loop, tools and context management. This adapter only
starts it in the selected project, streams its output into the Run, and returns
the final status. Git delivery is not performed here.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import signal
import uuid
from pathlib import Path

from ai.coding import workspace
from core.config.settings import settings

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
MAX_OUTPUT_CHARS = 60_000


def _ensure_config(home: Path, base_url: str, model: str) -> None:
    config_dir = home / ".config" / "opencode"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "opencode.json"
    payload = {
        "$schema": "https://opencode.ai/config.json",
        "providers": {
            "omniaide": {
                "name": "OmniAide",
                "env": ["OMNIAIDE_OPENCODE_API_KEY"],
                "package": "@opencode/ai/providers/openai-compatible",
                "settings": {"baseURL": base_url},
                "models": {
                    model: {
                        "name": model,
                    }
                },
            }
        },
        "model": f"omniaide/{model}",
    }
    config_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(config_file, 0o644)
    workspace._hand_to_sandbox(config_dir, config_file)


def _resolve_project(user_id: int, project: str) -> Path:
    from ai.coding.loop import _resolve_project as resolve

    return resolve(user_id, project)


def _ensure_home(home: Path) -> None:
    for path in (home, home / ".config", home / ".local" / "share", home / ".cache", home / "bin"):
        path.mkdir(parents=True, exist_ok=True)
    try:
        workspace._hand_to_sandbox(home, home / ".config", home / ".local" / "share", home / ".cache", home / "bin")
    except Exception:
        pass


def _find_binary(home: Path) -> Path | None:
    configured = (settings.coding_opencode_bin or "").strip()
    candidates = [
        Path(configured).expanduser() if configured else None,
        home / ".local" / "opencode2" / "node_modules" / ".bin" / "opencode",
        home / ".local" / "opencode" / "node_modules" / ".bin" / "opencode",
        home / ".local" / "bin" / "opencode",
        home / "bin" / "opencode",
        Path("/data/agent-runtime/bin/opencode"),
        Path(shutil.which("opencode") or ""),
    ]
    for candidate in candidates:
        if candidate and candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _sandbox_prefix() -> list[str] | None:
    sandbox = workspace.sandbox_identity()
    if sandbox is None:
        if workspace.settings.coding_sandbox_enabled and workspace._euid() == 0:
            return None
        return []
    setpriv = shutil.which("setpriv")
    if not setpriv:
        return None
    try:
        import grp
        import pwd

        user_entry = pwd.getpwnam(sandbox[0])
        group_entry = grp.getgrnam(sandbox[1])
    except Exception:
        return None
    return [
        setpriv,
        "--reuid", str(user_entry.pw_uid),
        "--regid", str(group_entry.gr_gid),
        "--clear-groups",
        "--",
    ]


async def _pump(stream, parts: list[str], *, emit) -> None:
    while True:
        line = await stream.readline()
        if not line:
            break
        text = ANSI_RE.sub("", line.decode("utf-8", errors="replace"))
        parts.append(text)
        if emit and text.strip():
            await emit("partial", {"content": text})


async def run_opencode(run, bot, coding_run, *, on_event, is_cancelled) -> dict:
    try:
        project = _resolve_project(run.user_id, coding_run.project_path or "")
    except Exception as exc:
        return {"status": "failed", "output": None, "error": str(exc)}

    home = Path(settings.coding_agent_home or "/data/agent-runtime/home").expanduser()
    try:
        _ensure_home(home)
    except OSError as exc:
        return {"status": "failed", "output": None, "error": f"agent home is not writable: {exc}"}

    binary = _find_binary(home)
    if binary is None:
        return {
            "status": "failed",
            "output": None,
            "error": (
                "OpenCode 未安装。请安装到 "
                f"{home}/.local/bin/opencode 或设置 CODING_OPENCODE_BIN。"
            ),
        }

    prefix = _sandbox_prefix()
    if prefix is None:
        return {"status": "failed", "output": None, "error": "setpriv unavailable; refusing to run OpenCode as root"}

    base_url = (
        settings.coding_opencode_base_url
        or settings.coding_base_url
        or settings.llm_base_url
    )
    api_key = (
        settings.coding_opencode_api_key
        or settings.coding_api_key
        or settings.llm_api_key
    )
    model = (
        settings.coding_opencode_model
        or settings.coding_model
        or settings.llm_model
    )
    if not base_url or not api_key or not model:
        return {
            "status": "failed",
            "output": None,
            "error": (
                "OpenCode 缺少模型配置。请设置 CODING_OPENCODE_BASE_URL、"
                "CODING_OPENCODE_API_KEY、CODING_OPENCODE_MODEL，"
                "或复用 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL。"
            ),
        }
    try:
        _ensure_config(home, base_url, model)
    except OSError as exc:
        return {"status": "failed", "output": None, "error": f"cannot write OpenCode config: {exc}"}

    argv = [str(binary), "--standalone", "run", "--auto"]
    model_ref = model if "/" in model else f"omniaide/{model}"
    argv.extend(["-m", model_ref])
    session_id = getattr(coding_run, "session_id", None)
    if session_id:
        from core.sessions import service as session_service

        session = await session_service.get_session(run.user_id, session_id)
        meta = (session or {}).get("metadata") or {}
        opencode_session = str(meta.get("opencode_session_id") or "")
        if not opencode_session:
            opencode_session = "ses_" + uuid.uuid4().hex
            await session_service.update_session(
                run.user_id,
                session_id,
                metadata={"opencode_session_id": opencode_session},
            )
        argv.extend(["--session", opencode_session])
    if settings.coding_opencode_agent:
        argv.extend(["--agent", settings.coding_opencode_agent])
    argv.append(run.input or "")

    env = workspace.sandbox_env()
    env.update({
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "OMNIAIDE_OPENCODE_BASE_URL": base_url,
        "OMNIAIDE_OPENCODE_API_KEY": api_key,
        "OMNIAIDE_OPENCODE_MODEL": model,
    })
    env["PATH"] = f"{binary.parent}:{home / '.local' / 'bin'}:{env.get('PATH', '')}"

    try:
        proc = await asyncio.create_subprocess_exec(
            *prefix,
            *argv,
            cwd=str(project),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        return {"status": "failed", "output": None, "error": f"cannot start OpenCode: {exc}"}

    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    cancelled = False

    async def watch_cancel():
        nonlocal cancelled
        while proc.returncode is None:
            if await is_cancelled():
                cancelled = True
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    pass
                return
            await asyncio.sleep(1)

    tasks = [
        asyncio.create_task(_pump(proc.stdout, stdout_parts, emit=on_event)),
        asyncio.create_task(_pump(proc.stderr, stderr_parts, emit=None)),
        asyncio.create_task(proc.wait()),
        asyncio.create_task(watch_cancel()),
    ]
    timeout = max(int(settings.coding_agent_timeout_seconds or 1800), 60)
    timed_out = False
    try:
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=timeout)
    except asyncio.TimeoutError:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

    if cancelled:
        return {"status": "cancelled", "output": "".join(stdout_parts)[-MAX_OUTPUT_CHARS:] or None, "error": None}
    if timed_out:
        return {"status": "failed", "output": "".join(stdout_parts)[-MAX_OUTPUT_CHARS:] or None, "error": f"OpenCode timed out after {timeout}s"}

    output = "".join(stdout_parts).strip()
    error_text = "".join(stderr_parts).strip()
    code = proc.returncode or 0
    await on_event(
        "step",
        {
            "name": "opencode",
            "arguments": {
                "model": settings.coding_opencode_model or None,
                "agent": settings.coding_opencode_agent or None,
            },
            "result": f"exit={code}" + (f"\n{error_text[-4000:]}" if error_text else ""),
            "status": "ok" if code == 0 else "error",
        },
    )
    if code != 0:
        return {
            "status": "failed",
            "output": output[-MAX_OUTPUT_CHARS:] or None,
            "error": (error_text[-4000:] or f"OpenCode exited with code {code}"),
        }
    return {"status": "done", "output": output[-MAX_OUTPUT_CHARS:] or "OpenCode finished.", "error": None}
