"""Small helper around the DingTalk Workspace CLI (`dws`)."""

from __future__ import annotations

import asyncio
import json
import os
import shutil


class DwSError(RuntimeError):
    pass


def _command(args: list[str]) -> list[str]:
    binary = os.environ.get("DWS_BIN") or shutil.which("dws") or "dws"
    if os.name == "nt":
        import subprocess
        return ["cmd.exe", "/d", "/s", "/c", subprocess.list2cmdline([binary, *args])]
    return [binary, *args]


async def _execute(args: list[str], timeout: float) -> tuple[str, str, int]:
    proc = await asyncio.create_subprocess_exec(
        *_command(args),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        raise DwSError(f"dws 超时: {' '.join(args[:3])}")
    return (
        out.decode("utf-8", errors="replace").strip(),
        err.decode("utf-8", errors="replace").strip(),
        proc.returncode,
    )


def _failure_message(stdout: str, stderr: str, returncode: int) -> str:
    message = stderr or stdout or f"dws exited {returncode}"
    try:
        payload = json.loads(message)
        message = payload.get("error", {}).get("message") or message
    except Exception:
        pass
    return message[:1000]


async def run_dws(args: list[str], timeout: float = 60.0) -> dict:
    stdout, stderr, returncode = await _execute(args, timeout)
    if returncode != 0:
        raise DwSError(_failure_message(stdout, stderr, returncode))
    if not stdout:
        return {}
    try:
        return json.loads(stdout)
    except Exception as e:
        raise DwSError(f"dws 返回非 JSON: {stdout[:300]} ({e})")


async def run_dws_text(args: list[str], timeout: float = 60.0) -> str:
    """Run a command whose output is human-readable text (help/schema)."""
    stdout, stderr, returncode = await _execute(args, timeout)
    if returncode != 0:
        raise DwSError(_failure_message(stdout, stderr, returncode))
    return stdout
